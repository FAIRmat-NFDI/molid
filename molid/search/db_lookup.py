import os
import logging
from typing import Dict, Any, List, Optional
from molid.db.sqlite_manager import DatabaseManager

logger = logging.getLogger(__name__)

CACHE_TABLE = 'cached_molecules'
OFFLINE_TABLE_MASTER = 'compound_data'

# _OFFLINE_FIELDS: Dict[str, str] = {
#     'inchikey': 'InChIKey',
#     'inchikey14': 'InChIKey14',
#     'inchi': 'InChI',
#     'smiles': 'SMILES',
#     'formula': 'Formula',
# }

_CACHE_FIELDS: Dict[str, str] = {
    'cid': 'CID',
    'inchikey': 'InChIKey',
    'inchikey14': 'InChIKey14',
    'molecularformula': 'MolecularFormula',
    'inchi': 'InChI',
    'tpsa': 'TPSA',
    'charge': 'Charge',
    'canonicalsmiLES': 'CanonicalSMILES',
    'isomericsmiles': 'IsomericSMILES',
    'title': 'Title',
    'iupacname': 'IUPACName',
    'xlogp': 'XLogP',
    'exactmass': 'ExactMass',
    'complexity': 'Complexity',
    'monoisotopicmass': 'MonoisotopicMass',
}

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
        return [result]

    # Fallback to InChIKey14 prefix match
    return [mgr.query_one(
        f"SELECT * FROM {OFFLINE_TABLE_MASTER} WHERE InChIKey14 = ?",
        [id_value[:14]]
    )]


def advanced_search(
    db_file: str,
    id_type: str,
    id_value: str
) -> List[Dict[str, Any]]:
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
    return None