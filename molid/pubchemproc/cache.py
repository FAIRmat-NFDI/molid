from __future__ import annotations

import logging
from typing import Any

from molid.search.db_lookup import advanced_search
from molid.db.db_utils import insert_dict_records
from molid.db.sqlite_manager import DatabaseManager
from molid.db.schema import NUMERIC_FIELDS
from molid.utils.formula import canonicalize_formula
from molid.utils.conversion import coerce_numeric_fields

logger = logging.getLogger(__name__)

CACHE_TABLE = 'cached_molecules'

def store_cached_data(
    cache_db_file: str,
    id_type: str,
    id_value: str,
    api_data: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Store the API response in the cache database.
    """
    if not isinstance(api_data, list) or not all(isinstance(item, dict) for item in api_data):
        logger.error(
            "Unexpected API response format for %s (%s): expected List[dict], got %r",
            id_type, id_value, type(api_data)
        )
        raise ValueError("Unexpected API response format; expected a list of dicts.")

    # If searching by CAS, make sure each stored record carries the CAS RN.
    if id_type.lower() == "cas":
        for item in api_data:
            item.setdefault("CAS", str(id_value))

    cleaned_records = [coerce_numeric_fields(item, NUMERIC_FIELDS) for item in api_data]
    insert_dict_records(
        db_file=cache_db_file,
        table=CACHE_TABLE,
        records=cleaned_records,
        ignore_conflicts=True
    )

    logger.info("Cached %d records for %s (%s)", len(api_data), id_type, id_value)

    # If a row already existed (INSERT OR IGNORE), upsert CAS onto it
    if id_type.lower() == "cas":
        mgr = DatabaseManager(cache_db_file)
        for item in api_data:
            cid = item.get("CID")
            ik  = item.get("InChIKey")
            if cid is not None:
                mgr.execute("UPDATE cached_molecules SET CAS = ? WHERE CID = ?", [id_value, cid])
            if ik:
                mgr.execute("UPDATE cached_molecules SET CAS = ? WHERE InChIKey = ?", [id_value, ik])

    cached = advanced_search(cache_db_file, id_type, id_value)
    logger.debug("cached results: %s, for %s, %s", cached, id_type, id_value)
    if not cached and id_type.lower() == "molecularformula":
        cached = advanced_search(cache_db_file, "molecularformula", canonicalize_formula(str(id_value)))

    if not cached:
        logger.warning(
            "Failed to retrieve just-stored cache record for %s (%s)",
            id_type, id_value
        )
    return cached


def get_cached_or_fetch(
    cache_db_file: str,
    id_type: str,
    id_value: str,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Checks for a cached molecule; if not found, fetches data via the API
    and stores it.
    Returns (record, from_cache).
    """
    if id_type.lower() == "molecularformula":
        canon = canonicalize_formula(str(id_value))
        cached = advanced_search(cache_db_file, id_type, canon)
        if cached:
            return cached, True

    cached = advanced_search(cache_db_file, id_type, id_value)
    if cached:
        return cached, True

    from molid.pubchemproc.fetch import fetch_molecule_data
    api_data = fetch_molecule_data(id_type, id_value)
    stored = store_cached_data(cache_db_file, id_type, id_value, api_data)
    return stored, False
