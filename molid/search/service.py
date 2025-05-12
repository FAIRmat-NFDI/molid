import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, Tuple, Union

from molid.pubchem_api.offline import basic_offline_search, advanced_offline_search
from molid.pubchem_api.cache import get_cached_or_fetch
from molid.db.db_utils import create_cache_db
from molid.pubchem_api.fetch import fetch_molecule_data
from molid.utils.conversion import convert_to_inchikey

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

    mode: str  # offline-basic | offline-advanced | online-only | online-cached
    cache_enabled: bool = False


# ---------------------------------------------------------------------------
# Helper that normalises *any* caller input
# ---------------------------------------------------------------------------

def _coerce_filters(
    raw: Union[str, Dict[str, str]], = "inchikey",
) -> Dict[str, str]:
    if isinstance(raw, dict):
        return raw                     # already OK
    if "=" in raw:                     # filter string
        return {k: v for k, v in (p.split("=", 1) for p in raw.split(","))}

    return {id_type.capitalize(): raw}


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
        cache_db:   str,
        cfg:       SearchConfig
    ) -> None:
        self.master_db = master_db
        self.cache_db   = cache_db
        self.cfg       = cfg

        # Fail fast if the selected mode requires files that are not present.
        self._ensure_required_files()

        # Make sure the cache schema exists *before* we might write to it.
        if self.cfg.mode == "online-cached" and self.cfg.cache_enabled:
            create_cache_db(self.cache_db)

        # Dispatch table keeps :py:meth:`search` straightforward.
        self._dispatch = {
            "offline-basic": self._search_offline_basic,
            "offline-advanced": self._search_offline_advanced,
            "online-only": self._search_online_only,
            "online-cached": self._search_online_cached,
        }

        if self.cfg.mode not in self._dispatch:
            raise ValueError(f"Unknown mode: {self.cfg.mode!r}")

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def search(self, input) -> Tuple[Any, str]:
        """Resolve input according to the configured mode.
        """
        logger.debug("Search request: id=%s (type=%s) via %s", input, self.cfg.mode)
        return self._dispatch[self.cfg.mode](input)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_required_files(self) -> None:
        """Verify that mandatory database files exist for the selected mode."""
        if self.cfg.mode.startswith("offline") and not os.path.isfile(self.master_db):
            raise DatabaseNotFound(
                f"Master DB not found at {self.master_db!s} (required for offline modes)."
            )

        # Cache DB presence is optional until we *write* to it.
        if self.cfg.mode == "online-cached" and self.cfg.cache_enabled:
            cache_dir = os.path.dirname(self.cache_db) or "."
            os.makedirs(cache_dir, exist_ok=True)

    def _unify_input_offline_basic(input):
        id_type = list(input.keys())[0].lower()
        identifier = list(input.values())[0]

        if id_type not in ("inchikey", "inchi", "smiles"):
            raise ValueError(
                "offline-basic only supports input of 'InChIkey', InChI or Smiles (not case sensitive); "
                f"received {id_type!r}."
            )
        if id_type != "inchikey":
            inchikey = convert_to_inchikey(identifier, id_type)
        else:
            inchikey = input
        return inchikey

    def _unify_input_offline_advanced(input):
        input_upper_case = {k.upper(): v for k, v in input.items()}

        if id_type not in ("inchikey", "inchi", "smiles"):
            raise ValueError(
                "offline-basic only supports input of 'InChIkey', InChI or Smiles (not case sensitive); "
                f"received {id_type!r}."
            )
        if id_type != "inchikey":
            inchikey = convert_to_inchikey(identifier, id_type)
        else:
            inchikey = input
        return inchikey

    # ------------------------------------------------------------------
    # Mode‑specific implementations
    # ------------------------------------------------------------------

    def _search_offline_basic(self, input):
        inchikey = self._unify_input_offline_basic(input)
        record = basic_offline_search(self.master_db, inchikey)
        if not record:
            raise MoleculeNotFound(f"{input!s} not found in master DB.")
        return record, "offline-basic"

    def _search_offline_advanced(self, input):
        results = advanced_offline_search(self.cache_db, identifiers)
        if not results:
            raise MoleculeNotFound(
                "No compounds matched filters: "
                + ", ".join(f"{k}={v}" for k, v in filters.items())
            )
        return results, "offline-advanced"

    def _search_online_only(self, input):
        data = fetch_molecule_data(input, id_type)
        props = data.get("PropertyTable", {}).get("Properties", [])
        if not props:
            raise MoleculeNotFound(f"No PubChem results for {input!s}.")
        return props[0], "api"

    def _search_online_cached(self, input):
        rec, from_cache = get_cached_or_fetch(self.cache_db, input, id_type)
        return rec, "user-cache" if from_cache else "api"

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_filters(input) -> Dict[str, str]:
        """Convert a comma‑separated filter string into a dict."""
         # e.g. input="Formula=C6H6,SMILES=c1ccccc1"
        filters: Dict[str, str] = {}
        for part in input.split(","):
            if "=" not in part:
                raise ValueError(f"Invalid filter expression: {part!r}")
            key, value = part.split("=", 1)
            if not key or not value:
                raise ValueError(f"Malformed filter segment: {part!r}")
            filters[key] = value
        return filters
