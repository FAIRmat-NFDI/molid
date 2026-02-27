from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path

from collections.abc import Callable
from typing import Any

from molid.search.db_lookup import basic_offline_search, advanced_search
from molid.pubchemproc.cache import get_cached_or_fetch, store_cached_data
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
    """Runtime configuration for SearchService (ordered backends)."""

    sources: list[str]
    cache_writes: bool = True


# ---------------------------------------------------------------------------
# Main service entry‑point
# ---------------------------------------------------------------------------


class SearchService:
    """High‑level interface for MolID look‑ups across all supported backends."""

    # ---------------------------------------------------------------------
    # Construction / validation
    # ---------------------------------------------------------------------

    def __init__(self, master_db: str, cache_db: str, cfg: SearchConfig) -> None:
        self.master_db = master_db
        self.cache_db = cache_db
        self.cfg = cfg

        # If write-through caching is enabled and api may be used, ensure cache schema exists.
        src = [s.lower() for s in (self.cfg.sources or [])]
        need_cache = ("cache" in src) or ("api" in src and bool(self.cfg.cache_writes))
        if need_cache:
            create_cache_db(self.cache_db)

        # Fail fast if requested sources require local files.
        self._ensure_required_files()

        self._dispatch: dict[
            str, Callable[[dict[str, Any]], tuple[list[dict[str, Any]], str]]
        ] = {
            "master": self._search_master,
            "cache": self._search_cache,
            "api": self._search_api,
        }

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def search(self, query: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        """Resolve query by walking configured sources in order."""
        logger.debug("Search request via sources=%s: %s", self.cfg.sources, query)

        # Validate input: exactly one key
        if not isinstance(query, dict):
            raise TypeError("query must be a dict of one key/value.")
        if len(query) != 1:
            raise ValueError(f"Expected exactly 1 search parameter, got {len(query)}.")

        query_lc = {k.lower(): v for k, v in query.items()}
        sources = [s.lower() for s in (self.cfg.sources or [])]
        if not sources:
            raise ValueError(
                "No sources configured. Set AppConfig.sources to e.g. ['cache','api']."
            )

        for tier in sources:
            # 1) Quick availability/permission gates (same as before)
            if tier == "master" and not _has_readable_file(self.master_db):
                logger.debug("Skip master: master DB missing/unreadable")
                continue
            if tier == "cache" and not _has_readable_file(self.cache_db):
                logger.debug("Skip cache: cache DB missing/unreadable")
                continue
            if tier == "api":
                if self.cfg.cache_writes and not _is_writable_dir(self.cache_db):
                    logger.debug(
                        "api cache writes disabled (cache dir not writable); proceeding without writes"
                    )

            # 2) Execute tier
            try:
                logger.debug("Tier %s: dispatch with %s", tier, query_lc)
                records, source = self._dispatch[tier](query_lc)
            except UnsupportedIdentifierForMode as e:
                logger.debug("Skip %s: %s", tier, e)
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
        raise MoleculeNotFound("All configured sources exhausted with no result.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_required_files(self) -> None:
        """Verify local artifacts exist for requested sources."""
        src = [s.lower() for s in (self.cfg.sources or [])]
        if "master" in src and not os.path.isfile(self.master_db):
            raise DatabaseNotFound(f"Master DB not found at {self.master_db!r}.")
        if "cache" in src and not os.path.isfile(self.cache_db):
            raise DatabaseNotFound(f"Cache DB not found at {self.cache_db!r}.")
        # If we write cache (api+cache_writes), ensure directory exists
        if "api" in src and self.cfg.cache_writes:
            cache_dir = os.path.dirname(self.cache_db) or "."
            os.makedirs(cache_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Mode‑specific implementations
    # ------------------------------------------------------------------

    def _search_master(self, input: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        id_type, id_value = normalize_query(input, "basic")
        if id_type == "molecularformula":
            id_value = canonicalize_formula(str(id_value))
        record = basic_offline_search(self.master_db, id_type, id_value)
        if not record:
            raise MoleculeNotFound(f"{input!s} not found in master DB.")
        return record, "master"

    def _search_cache(self, input: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        id_type, id_value = normalize_query(input, "advanced")
        if id_type == "molecularformula":
            id_value = canonicalize_formula(str(id_value))
        results = advanced_search(self.cache_db, id_type, id_value)
        if not results:
            raise MoleculeNotFound(
                "No compounds matched identifier: "
                + ", ".join(f"{k}={v}" for k, v in input.items())
            )
        return results, "cache"

    def _search_api(self, input: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        id_type, id_value = normalize_query(input, "advanced")
        if id_type == "molecularformula":
            id_value = canonicalize_formula(str(id_value))

        # If user put "cache" before "api", we might already have it;
        # but if they skipped "cache" we can still honor read-through when desired.
        if self.cfg.cache_writes and _has_readable_file(self.cache_db):
            rec, from_cache = get_cached_or_fetch(self.cache_db, id_type, id_value)
            if rec:
                return rec, ("cache" if from_cache else "API")

        data = fetch_molecule_data(id_type, id_value)
        if not data:
            raise MoleculeNotFound(f"No PubChem results for {id_type}={id_value!r}.")

        if self.cfg.cache_writes:
            try:
                create_cache_db(self.cache_db)
                stored = store_cached_data(self.cache_db, id_type, id_value, data)
                return (stored or data), "API"
            except Exception:
                logger.debug(
                    "store_cached_data failed; returning API data", exc_info=True
                )
        return data, "API"
