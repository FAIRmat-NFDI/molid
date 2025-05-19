import logging
from typing import Tuple, Dict, Any
from molid.db.sqlite_manager import DatabaseManager
from molid.search.db_lookup import advanced_search
from molid.db.db_utils import insert_dict_records

logger = logging.getLogger(__name__)

CACHE_TABLE = 'cached_molecules'

def store_cached_data(
    cache_db_file: str,
    id_type: str,
    id_value: str,
    api_data: dict
) -> Dict[str, Any]:
    """
    Store the API response in the cache database.
    """
    if not isinstance(api_data, dict):
        logger.error("Unexpected API response format for %s (%s)", id_type, id_value)
        raise ValueError("Unexpected API response format.")

    insert_dict_records(
        db_file=cache_db_file,
        table=CACHE_TABLE,
        records=[api_data],
        ignore_conflicts=False
    )

    logger.info("Cached data for %s (%s)", id_type, id_value)

    cached = advanced_search(cache_db_file, id_type, id_value, table=CACHE_TABLE)
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
) -> Tuple[Dict[str, Any], bool]:
    """
    Checks for a cached molecule; if not found, fetches data via the API
    and stores it.
    Returns (record, from_cache).
    """
    cached = advanced_search(cache_db_file, id_type, id_value, table=CACHE_TABLE)
    if cached:
        return cached, True

    from molid.pubchem_api.fetch import fetch_molecule_data
    api_data = fetch_molecule_data(id_type, id_value)
    stored = store_cached_data(cache_db_file, id_type, id_value, api_data)
    return stored, False
