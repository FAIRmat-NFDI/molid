from __future__ import annotations

import os
import logging
import warnings

from typing import Any
from molid.db.sqlite_manager import DatabaseManager

logger = logging.getLogger(__name__)

CACHE_TABLE = 'cached_molecules'
OFFLINE_TABLE_MASTER = 'compound_data'

_CACHE_FIELDS: dict[str, str] = {
    'cid': 'CID',
    'inchikey': 'InChIKey',
    'cas': 'CAS',
    'molecularformula': 'MolecularFormula',
    'inchi': 'InChI',
    'tpsa': 'TPSA',
    'charge': 'Charge',
    'smiles': 'SMILES',
    'name': 'Title',
    'iupacname': 'IUPACName',
    'xlogp': 'XLogP',
    'exactmass': 'ExactMass',
    'complexity': 'Complexity',
    'monoisotopicmass': 'MonoisotopicMass',
}

def basic_offline_search(
    offline_db_file: str,
    id_value: str
) -> list[dict[str, Any]]:
    """
    Query the offline full PubChem database for a given InChIKey or InChIKey14.
    """
    if not os.path.exists(offline_db_file):
        logger.debug("Offline DB not found at %s", offline_db_file)
        return []

    mgr = DatabaseManager(offline_db_file)
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

    # No match
    return []


def advanced_search(
    db_file: str,
    id_type: str,
    id_value: str
) -> list[dict[str, Any]]:
    """
    Query SQLite database 'db_file' on table 'table' for rows matching id_type = id_value.
    """
    if not os.path.exists(db_file):
        logger.debug("DB file %s does not exist", db_file)
        return []
    fields_map = _CACHE_FIELDS

    column = fields_map.get(id_type.lower())
    if not column:
        raise ValueError(f"Unsupported search field '{id_type}' for table '{CACHE_TABLE}'")

    mgr = DatabaseManager(db_file)
    sql = f"SELECT * FROM {CACHE_TABLE} WHERE {column} = ?"
    results = mgr.query_all(sql, [id_value])
    if results:
        return [
            {k: v for k, v in record.items() if v is not None}
            for record in results
        ]
    return []