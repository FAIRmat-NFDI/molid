from __future__ import annotations

import os
import logging
import warnings

from typing import Any
from molid.db.sqlite_manager import DatabaseManager
from molid.db.schema import CACHE_COLUMNS, OFFLINE_COLUMNS

logger = logging.getLogger(__name__)

CACHE_TABLE = 'cached_molecules'
OFFLINE_TABLE_MASTER = 'compound_data'
OFFLINE_TABLE_CAS    = 'cas_mapping'

def basic_offline_search(
    offline_db_file: str,
    id_type: str,
    id_value: str
) -> list[dict[str, Any]]:
    """
    Query SQLite database 'db_file' on table 'table' for rows matching id_type = id_value.
    """
    if not os.path.exists(offline_db_file):
        logger.debug("DB file %s does not exist", offline_db_file)
        return []

    if id_type == 'cas':
        # import pdb; pdb.set_trace()
        return master_lookup_by_cas(offline_db_file, id_value)

    mgr = DatabaseManager(offline_db_file)

    if id_type == "inchikey":
        # Try full InChIKey match first
        result = mgr.query_one(
            f"SELECT * FROM {OFFLINE_TABLE_MASTER} WHERE InChIKey = ?",
            [id_value])

        if result:
            return [result]

        # Fallback to InChIKey14 prefix match
        result = mgr.query_one(
            f"SELECT * FROM {OFFLINE_TABLE_MASTER} WHERE substr(InChIKey,1,14) = ?",
            [id_value[:14]])
        if result:
            warnings.warn(
            "basic_offline_search: full InChIKey lookup failed; "
            "falling back to InChIKey14 prefix match: this is a skeletal match – "
            "it ignores stereochemistry (and isotopic labels), so results may be ambiguous.",
            UserWarning)
            return [result]

    sql = f"SELECT * FROM {OFFLINE_TABLE_MASTER} WHERE {id_type} = ?"
    results = mgr.query_all(sql, [id_value])
    if results:
        return [
            {k: v for k, v in record.items() if v is not None}
            for record in results
        ]

    return []


def master_lookup_by_cas(offline_db_file: str, cas: str) -> list[dict[str, Any]]:
    """Return rows from compound_data joined via cas_mapping for the given CAS."""
    if not os.path.exists(offline_db_file):
        logger.debug("Offline DB not found at %s", offline_db_file)
        return []
    db = DatabaseManager(offline_db_file)
    sql = (f"SELECT cd.* FROM {OFFLINE_TABLE_CAS} cm "
           f"JOIN {OFFLINE_TABLE_MASTER} cd ON cd.CID = cm.CID "
           f"WHERE cm.CAS = ? ORDER BY (cm.source='synonym') DESC, cm.confidence DESC")
    rows = db.query_all(sql, [cas])
    return rows or []

def advanced_search(
    db_file: str,
    id_type: str,
    id_value: str
) -> list[dict[str, Any]]:
    """
    Query SQLite cache DB. Special handling:
      - CAS: resolve via cas_mapping (highest confidence, newest), LIMIT 1.
      - CID: enrich row with best CAS from mapping; fallback to row.CAS.
    """
    if not os.path.exists(db_file):
        logger.debug("DB file %s does not exist", db_file)
        return []

    mgr = DatabaseManager(db_file)

    key = (id_type or "").lower()
    if key == "cas":
        sql = (
            f"SELECT m.*, "
            f"( SELECT cm2.CAS FROM cas_mapping cm2 "
            f"  WHERE cm2.CID = m.CID "
            f"  ORDER BY (cm2.source='synonym') DESC, cm2.confidence DESC, cm2.updated_at DESC "
            f"  LIMIT 1"
            f") AS CAS, "
            f"cm.CAS AS MatchedCAS "
            f"FROM cas_mapping cm "
            f"JOIN {CACHE_TABLE} m ON m.CID = cm.CID "
            f"WHERE cm.CAS = ? "
            f"ORDER BY (cm.source='synonym') DESC, cm.confidence DESC, cm.updated_at DESC"
        )
        rows = mgr.query_all(sql, [id_value])
        # no fallback to m.CAS anymore (we don't write it)
        return [{k: v for k, v in r.items() if v is not None} for r in (rows or [])]

    if key == "cid":
        # Return one row; CAS is the best mapping (or existing row CAS as fallback)
        sql = (
            f"SELECT m.*, "
            f"( SELECT cm.CAS FROM cas_mapping cm "
            f"  WHERE cm.CID = m.CID "
            f"  ORDER BY (cm.source='synonym') DESC, cm.confidence DESC, cm.updated_at DESC "
            f"  LIMIT 1"
            f") AS CAS "
            f"FROM {CACHE_TABLE} m WHERE m.CID = ?"
        )
        rows = mgr.query_all(sql, [id_value])
        return [{k: v for k, v in r.items() if v is not None} for r in (rows or [])]

    # Default column-based lookup (SMILES alias handling preserved)
    columns = {c.lower(): c for c in CACHE_COLUMNS}
    if key == "smiles" and "canonicalsmiles" in columns:
        column = "canonicalsmiles"
    else:
        column = columns.get(key)

    if not column:
        raise ValueError(f"Unsupported search field '{id_type}' for table '{CACHE_TABLE}'")

    sql = f"SELECT m.*,( SELECT cm.CAS FROM cas_mapping cm WHERE cm.CID = m.CID ORDER BY (cm.source='synonym') DESC, cm.confidence DESC, cm.updated_at DESC LIMIT 1) AS CAS FROM cached_molecules m WHERE {column} = ?"
    results = mgr.query_all(sql, [id_value])
    if results:
        return [{k: v for k, v in rec.items() if v is not None} for rec in results]
    return []