import os
import re
import sqlite3
import logging
from typing import Tuple, Dict, Any, Optional, List

from molid.db.schema import CACHE_SCHEMA

logger = logging.getLogger(__name__)

CACHE_TABLE = 'cached_molecules'

def sanitize_identifier(identifier: str) -> str:
    """Sanitize a query identifier for safe and consistent caching."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", identifier)

def advanced_cache_search(cache_db_file: str, filters: Dict[str, Any]) -> List[Dict[str,Any]]:
    cols, vals = [], []
    for k,v in filters.items():
        cols.append(f"{k} = ?")
        vals.append(v)
    sql = f"SELECT * FROM {CACHE_TABLE} WHERE " + " AND ".join(cols)
    with sqlite3.connect(cache_db_file) as conn:
        cur = conn.execute(sql, vals)
        rows = cur.fetchall()
        if not rows:
            return []

        # get column names
        meta = conn.execute(f"PRAGMA table_info({CACHE_TABLE})").fetchall()
        colnames = [c[1] for c in meta]

        return [dict(zip(colnames,row)) for row in rows]


def get_cached_data(
    cache_db_file: str,
    query_identifier: str,
    query_type: str
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a molecule from the user-specific cache DB.
    """
    if not os.path.exists(cache_db_file):
        logger.debug("Cache DB %s does not exist", cache_db_file)
        return None

    try:
        with sqlite3.connect(cache_db_file) as conn:
            cursor = conn.execute(
                f"SELECT InChIKey, InChIKey14, MolecularFormula, InChI, CanonicalSMILES,"
                f" Title, IUPACName, MonoisotopicMass, IsomericSMILES, fetched_at"
                f" FROM {CACHE_TABLE} WHERE query_identifier = ? AND query_type = ?",
                (query_identifier, query_type)
            )
            row = cursor.fetchone()
        if not row:
            logger.debug("No cache hit for %s (%s)", query_identifier, query_type)
            return None

        keys = [
            "InChIKey", "InChIKey14", "MolecularFormula", "InChI",
            "CanonicalSMILES", "Title", "IUPACName",
            "MonoisotopicMass", "IsomericSMILES", "fetched_at"
        ]
        return dict(zip(keys, row))
    except sqlite3.Error as e:
        logger.error("Error querying cache DB %s: %s", cache_db_file, e)
        return None


def store_cached_data(
    cache_db_file: str,
    query_identifier: str,
    query_type: str,
    api_data: dict
) -> Dict[str, Any]:
    """
    Store the API response in the cache database.
    Extracts key fields for indexing.
    """
    try:
        props = api_data["PropertyTable"]["Properties"]
        record = props[0]
    except (KeyError, IndexError) as e:
        logger.error("Invalid API response format: %s", e)
        raise ValueError("Unexpected API response format.")

    data = {
        "MolecularFormula": record.get("MolecularFormula"),
        "InChI": record.get("InChI"),
        "InChIKey": record.get("InChIKey"),
        "InChIKey14": record.get("InChIKey14"),
        "CanonicalSMILES": record.get("CanonicalSMILES"),
        "IsomericSMILES": record.get("IsomericSMILES"),
        "Title": record.get("Title"),
        "IUPACName": record.get("IUPACName"),
        "MonoisotopicMass": record.get("MonoisotopicMass"),
    }

    placeholders = ", ".join("?" for _ in data)
    columns = ", ".join(data.keys())
    insert_query = (
        f"INSERT OR REPLACE INTO {CACHE_TABLE} "
        f"(query_identifier, query_type, {columns}) VALUES (?, ?, {placeholders})"
    )

    try:
        with sqlite3.connect(cache_db_file) as conn:
            conn.execute(
                insert_query,
                tuple([query_identifier, query_type] + list(data.values()))
            )
            conn.commit()
        logger.info("Cached data for %s (%s)", query_identifier, query_type)
    except sqlite3.Error as e:
        logger.error("Failed to store cache data in %s: %s", cache_db_file, e)
        raise

    cached = get_cached_data(cache_db_file, query_identifier, query_type)
    if not cached:
        logger.warning("Failed to retrieve just-stored cache record for %s (%s)", query_identifier, query_type)
    return cached  # type: ignore


def get_cached_or_fetch(
    cache_db_file: str,
    molecule_identifier: str,
    identifier_type: str
) -> Tuple[Dict[str, Any], bool]:
    """
    Checks for a cached molecule; if not found, fetches data via the API
    and stores it.
    Returns (record, from_cache).
    """
    safe_id = sanitize_identifier(molecule_identifier)

    cached = get_cached_data(cache_db_file, safe_id, identifier_type)
    if cached:
        return cached, True

    # Fallback to API
    from molid.pubchem_api.fetch import fetch_molecule_data

    try:
        api_data = fetch_molecule_data(molecule_identifier, identifier_type)
    except Exception as e:
        logger.error("API fetch error for %s (%s): %s", molecule_identifier, identifier_type, e)
        raise

    stored = store_cached_data(cache_db_file, safe_id, identifier_type, api_data)
    return stored, False
