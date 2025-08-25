from __future__ import annotations

import os
import logging
from dataclasses import dataclass

from collections.abc import Callable
from typing import Any, Iterable

from molid.search.db_lookup import basic_offline_search
from molid.pubchem_api.cache import get_cached_or_fetch
from molid.db.db_utils import create_cache_db
from molid.pubchem_api.fetch import fetch_molecule_data
from molid.utils.conversion import convert_to_inchikey
from molid.search.db_lookup import advanced_search

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class MoleculeNotFound(Exception):
    """Raised when a molecule cannot be located in the chosen backend."""


class DatabaseNotFound(Exception):
    """Raised when a required SQLite database file is missing."""


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class SearchConfig:
    """User‑supplied runtime configuration for a :class:`SearchService` instance."""

    mode: str  # offline-basic | offline-advanced | online-only | online-cached | auto
    auto_priority: list[str] | None = None


# ---------------------------------------------------------------------------
# Main service entry‑point
# ---------------------------------------------------------------------------

class SearchService:
    """High‑level interface for MolID look‑ups across all supported backends."""

    # ---------------------------------------------------------------------
    # Construction / validation
    # ---------------------------------------------------------------------

    def __init__(
        self,
        master_db: str,
        cache_db: str,
        cfg: SearchConfig
    ) -> None:
        self.master_db = master_db
        self.cache_db = cache_db
        self.cfg = cfg

        # Fail fast if the selected mode requires files that are not present.
        self._ensure_required_files()

        # Make sure the cache schema exists *before* we might write to it.
        if self.cfg.mode == "online-cached":
            create_cache_db(self.cache_db)

        self._dispatch: dict[str, Callable[[dict[str, Any]], tuple[list[dict[str, Any]], str]]] = {
            "offline-basic": self._search_offline_basic,
            "offline-advanced": self._search_offline_advanced,
            "online-only": self._search_online_only,
            "online-cached": self._search_online_cached,
        }

        if self.cfg.mode != "auto" and self.cfg.mode not in self._dispatch:
            raise ValueError(f"Unknown mode: {self.cfg.mode!r}")

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def search(self, query: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        """Resolve query according to the configured mode (or auto priority)."""
        logger.debug("Search request via %s: %s", self.cfg.mode, query)

        # Validate input: exactly one key
        if not isinstance(query, dict):
            raise TypeError("query must be a dict of one key/value.")
        if len(query) != 1:
            raise ValueError(f"Expected exactly 1 search parameter, got {len(query)}.")
        query_lc = {k.lower(): v for k, v in query.items()}

        # Direct mode
        if self.cfg.mode != "auto":
            mode = self.cfg.mode
            if mode not in self._dispatch:
                raise ValueError(f"Unknown mode: {mode!r}")
            return self._dispatch[mode](query_lc)

        # AUTO MODE
        priorities = self.cfg.auto_priority or ["offline-basic", "online-cached", "online-only"]

        for mode in priorities:
            if mode not in self._dispatch:
                logger.debug("AUTO: skipping unknown mode %s", mode)
                continue

            # Prereq checks (non-noisy skips)
            try:
                if mode == "offline-basic":
                    if not os.path.isfile(self.master_db):
                        logger.debug("AUTO: skip %s (no master DB at %s)", mode, self.master_db)
                        continue

                elif mode == "offline-advanced":
                    if not os.path.isfile(self.cache_db):
                        logger.debug("AUTO: skip %s (no cache DB at %s)", mode, self.cache_db)
                        continue

                elif mode == "online-cached":
                    # Ensure cache dir is writable (schema created lazily inside the mode)
                    cache_dir = os.path.dirname(self.cache_db) or "."
                    try:
                        os.makedirs(cache_dir, exist_ok=True)
                    except Exception as e:
                        logger.debug("AUTO: skip %s (cannot create cache dir %s: %s)", mode, cache_dir, e)
                        continue

                # online-only has no prereqs

                # Try the mode
                res, _used = self._dispatch[mode](query_lc)
                logger.info("AUTO: succeeded via %s", mode)
                return res, mode

            except (MoleculeNotFound, DatabaseNotFound) as e:
                logger.info("AUTO: %s yielded no result (%s); trying next...", mode, e)
                continue
            except Exception as e:
                logger.warning("AUTO: unexpected error in %s: %s; trying next...", mode, e)
                continue

        raise MoleculeNotFound("AUTO mode exhausted all strategies with no result.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_required_files(self) -> None:
        """Verify that mandatory database files exist for the selected mode."""
        mode = self.cfg.mode
        # offline-basic needs the master DB
        if mode == "offline-basic" and not os.path.isfile(self.master_db):
            raise DatabaseNotFound(
                f"Master DB not found at {self.master_db!r} (required for offline-basic)."
            )

        # offline-advanced needs the cache DB
        if mode == "offline-advanced" and not os.path.isfile(self.cache_db):
            raise DatabaseNotFound(
                f"Cache DB not found at {self.cache_db!r} (required for offline-advanced)."
            )

        # online-cached: ensure cache folder exists (file itself will be created later)
        if mode == "online-cached":
            cache_dir = os.path.dirname(self.cache_db) or "."
            os.makedirs(cache_dir, exist_ok=True)

    def _preprocess_input(
        self,
        input: dict[str, Any],
        mode: str
    ) -> tuple[str, Any]:
        """Normalize and convert identifiers based on mode (basic vs advanced)."""
        if mode == 'basic':
            id_types = ("inchikey", "inchi", "smiles")
        elif mode == 'advanced':
            id_types = ('cid', 'name', 'smiles', 'inchi', 'inchikey', 'molecularformula')

        id_type = list(input.keys())[0]
        id_value = list(input.values())[0]

        if id_type not in id_types:
            raise ValueError(
                f"search mode {mode} only supports input of {id_types} (not case sensitive); "
                f"received {id_type!r}."
            )

        if id_type in ("inchi", "smiles"):
            inchikey = convert_to_inchikey(id_value, id_type)
            return "inchikey", inchikey

        return id_type, id_value


    # ------------------------------------------------------------------
    # Mode‑specific implementations
    # ------------------------------------------------------------------

    def _search_offline_basic(
        self,
        input: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        __, id_value = self._preprocess_input(input, 'basic')
        record = basic_offline_search(self.master_db, id_value)
        if not record:
            raise MoleculeNotFound(f"{input!s} not found in master DB.")
        return record, self.cfg.mode

    def _search_offline_advanced(
        self,
        input: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        id_type, id_value = self._preprocess_input(input, 'advanced')
        results = advanced_search(self.cache_db, id_type, id_value)
        if not results:
            raise MoleculeNotFound(
                "No compounds matched identifier: "
                + ", ".join(f"{k}={v}" for k, v in input.items())
            )
        return results, self.cfg.mode

    def _search_online_only(
        self,
        input: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        id_type, id_value = self._preprocess_input(input, 'advanced')
        data = fetch_molecule_data(id_type, id_value)
        if not data:
            raise MoleculeNotFound(f"No PubChem results for {id_type, id_value}.")
        return data, self.cfg.mode

    def _search_online_cached(
        self,
        input: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        create_cache_db(self.cache_db)
        id_type, id_value = self._preprocess_input(input, 'advanced')
        rec, from_cache = get_cached_or_fetch(self.cache_db, id_type, id_value)
        if not rec:
            raise MoleculeNotFound(f"No PubChem results for {id_type}={id_value}.")

        # DEBUG log: record whether this hit came from cache or API
        source = 'cache' if from_cache else 'API'
        logger.debug(
            "SearchService._search_online_cached: "
            "identifier=%s, result_source=%s",
            {id_type: id_value}, source
        )
        return rec, self.cfg.mode
