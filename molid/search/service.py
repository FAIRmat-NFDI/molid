from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path

from collections.abc import Callable
from typing import Any

from molid.search.db_lookup import basic_offline_search, advanced_search
from molid.pubchemproc.cache import get_cached_or_fetch
from molid.db.db_utils import create_cache_db
from molid.pubchemproc.fetch import fetch_molecule_data
from molid.utils.identifiers import normalize_query, UnsupportedIdentifierForMode
from molid.utils.formula import canonicalize_formula

logger = logging.getLogger(__name__)

def _has_readable_file(p: str | None) -> bool:
    return bool(p) and os.path.isfile(p) and os.access(p, os.R_OK)

def _is_writable_dir(path: str | None) -> bool:
    d = Path(os.path.dirname(path) or ".")
    try:
        d.mkdir(parents=True, exist_ok=True)
        test = d / ".molid_writetest"
        with open(test, "w") as fh:
            fh.write("")
        test.unlink(missing_ok=True)  # py>=3.8
        return True
    except Exception:
        return False
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
        mode = (self.cfg.mode or "").lower()

        # Direct mode
        if self.cfg.mode != "auto":
            mode = self.cfg.mode
            if mode not in self._dispatch:
                raise ValueError(f"Unknown mode: {mode!r}")
            return self._dispatch[mode](query_lc)

        # AUTO MODE
        priority = (self.cfg.auto_priority
                    or ["offline-basic", "online-cached", "online-only"])

        for tier in priority:
            # 1) Quick availability/permission gates (same as before)
            if tier.startswith("offline"):
                if not _has_readable_file(self.master_db):
                    logger.debug("Skip %s: master DB missing/unreadable", tier)
                    continue
                if tier == "offline-advanced" and not _has_readable_file(self.cache_db):
                    logger.debug("Skip %s: cache DB missing/unreadable", tier)
                    continue

            if tier == "online-cached":
                # allow lazy creation, but ensure parent dir is writable
                if not _is_writable_dir(self.cache_db):
                    logger.debug("Skip online-cached: cache dir not writable; falling through")
                    continue

            # 2) Execute tier
            try:
                logger.debug("Tier %s: dispatch with %s", tier, query_lc)
                records, source = self._dispatch[tier](query_lc)
            except UnsupportedIdentifierForMode as e:
                logger.debug("Skip %s: %s", tier, e)  # 👈 quietly skip this tier
                continue
            except (MoleculeNotFound, DatabaseNotFound) as e:
                logger.info("Tier %s yielded no result: %s; falling through", tier, e)
                continue
            except FileNotFoundError:
                logger.debug("Tier %s resource missing; falling through", tier)
                continue
            except PermissionError:
                logger.debug("Tier %s permission error; falling through", tier)
                continue
            except Exception:
                logger.exception("Tier %s failed hard; aborting", tier)
                raise

            if not records:
                logger.debug("Tier %s returned 0 results; trying next tier", tier)
                continue

            logger.info("Resolved via %s with %d results", tier, len(records))
            return records, source

        # Nothing matched
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

    # ------------------------------------------------------------------
    # Mode‑specific implementations
    # ------------------------------------------------------------------

    def _search_offline_basic(
        self,
        input: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        print(input)
        id_type, id_value = normalize_query(input, 'basic')
        record = basic_offline_search(self.master_db, id_type, id_value)
        if not record:
            raise MoleculeNotFound(f"{input!s} not found in master DB.")
        return record, 'master'

    def _search_offline_advanced(
        self,
        input: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        id_type, id_value = normalize_query(input, 'advanced')
        if id_type == "molecularformula":
            id_value = canonicalize_formula(str(id_value))
        results = advanced_search(self.cache_db, id_type, id_value)
        if not results:
            raise MoleculeNotFound(
                "No compounds matched identifier: "
                + ", ".join(f"{k}={v}" for k, v in input.items())
            )
        return results, 'cache'

    def _search_online_only(
        self,
        input: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        id_type, id_value = normalize_query(input, 'advanced')
        if id_type == "molecularformula":
            id_value = canonicalize_formula(str(id_value))
        data = fetch_molecule_data(id_type, id_value)
        if not data:
            raise MoleculeNotFound(f"No PubChem results for {id_type}={id_value!r}.")
        return data, 'API'


    def _search_online_cached(
        self,
        input: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        create_cache_db(self.cache_db)
        id_type, id_value = normalize_query(input, 'advanced')
        if id_type == "molecularformula":
            id_value = canonicalize_formula(str(id_value))
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
        return rec, source
