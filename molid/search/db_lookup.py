# molid/search/db_lookup.py

import os
import logging
from typing import Dict, Any, List, Optional
from molid.db.database_manager import DatabaseManager

logger = logging.getLogger(__name__)

CACHE_TABLE = 'cached_molecules'
OFFLINE_TABLE_MASTER = 'compound_data'


def basic_offline_search(
    offline_db_file: str,
    id_value: str
) -> Optional[Dict[str, Any]]:
    """
    Query the offline full PubChem database for a given InChIKey or InChIKey14.
    """
    if not os.path.exists(offline_db_file):
        logger.debug("Offline DB not found at %s", offline_db_file)
        return None

    mgr = DatabaseManager(offline_db_file)
    # Try full InChIKey match first
    result = mgr.query_one(
        f"SELECT * FROM {OFFLINE_TABLE_MASTER} WHERE InChIKey = ?",
        [id_value]
    )
    if result:
        return result

    # Fallback to InChIKey14 prefix match
    return mgr.query_one(
        f"SELECT * FROM {OFFLINE_TABLE_MASTER} WHERE InChIKey14 = ?",
        [id_value[:14]]
    )


def advanced_search(
    db_file: str,
    id_type: str,
    id_value: str,
    table: str = CACHE_TABLE
) -> List[Dict[str, Any]]:
    """
    Query SQLite database 'db_file' on table 'table' for rows matching id_type = id_value.
    """
    if not os.path.exists(db_file):
        logger.debug("DB file %s does not exist", db_file)
        return []

    mgr = DatabaseManager(db_file)
    return mgr.query_all(
        f"SELECT * FROM {table} WHERE {id_type} = ?",
        [id_value]
    )