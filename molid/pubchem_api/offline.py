import os
import sqlite3
from typing import Any, Dict, Optional, List

OFFLINE_TABLE_MASTER = 'compound_data'
CACHE_TABLE = 'cached_molecules'
_column_cache: Optional[List[str]] = None  # Global cache for column names


def basic_offline_search(
    offline_db_file: str,
    molecule_identifier: str
) -> Optional[Dict[str, Any]]:
    """
    Query the offline full PubChem database for a given InChIKey or InChIKey14.
    Returns a dict of all columns if found, else None.
    """
    if not os.path.exists(offline_db_file):
        return None

    global _column_cache

    with sqlite3.connect(offline_db_file) as conn:
        cursor = conn.cursor()

        # Try full InChIKey match
        cursor.execute(
            f"SELECT * FROM {OFFLINE_TABLE_MASTER} WHERE InChIKey = ?",
            (molecule_identifier,)
        )
        row = cursor.fetchone()

        # Fallback to InChIKey14 prefix match
        if not row:
            cursor.execute(
                f"SELECT * FROM {OFFLINE_TABLE_MASTER} WHERE InChIKey14 = ?",
                (molecule_identifier[:14],)
            )
            row = cursor.fetchone()

        if not row:
            return None

        # Cache column names only once
        if _column_cache is None:
            cursor.execute(f"PRAGMA table_info({OFFLINE_TABLE_MASTER})")
            _column_cache = [col[1] for col in cursor.fetchall()]

        return dict(zip(_column_cache, row))

def advanced_offline_search(
    db_file: str,
    filters: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    filters might be like {"Formula": "C6H6", "SMILES": "c1ccccc1"}.
    Build a WHERE clause over only the provided keys.
    """
    cols = []
    vals = []
    for col, val in filters.items():
        cols.append(f"{col} = ?")
        vals.append(val)
    sql = f"SELECT * FROM {CACHE_TABLE} WHERE " + " AND ".join(cols)
    with sqlite3.connect(db_file) as conn:
        cursor = conn.execute(sql, vals)
        rows = cursor.fetchall()

        # if no matches, return empty list
        if not rows:
            return []

        # ensure column names are loaded
        global _column_cache
        if _column_cache is None:
            meta = conn.execute(f"PRAGMA table_info({CACHE_TABLE})").fetchall()
            _column_cache = [col[1] for col in meta]

        # map each row to dict
        return [dict(zip(_column_cache, row)) for row in rows]