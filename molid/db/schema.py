"""
Centralized SQL schema definitions for MolID's SQLite databases.
"""

OFFLINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS compound_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    SMILES TEXT,
    InChIKey TEXT UNIQUE,
    InChI TEXT,
    Formula TEXT,
    InChIKey14 TEXT
);
CREATE INDEX IF NOT EXISTS idx_inchikey ON compound_data(InChIKey);
CREATE INDEX IF NOT EXISTS idx_inchikey14 ON compound_data(InChIKey14);

CREATE TABLE IF NOT EXISTS processed_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_name TEXT UNIQUE NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cached_molecules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_identifier TEXT,
    query_type TEXT,
    InChIKey TEXT,
    InChIKey14 TEXT,
    MolecularFormula TEXT,
    InChI TEXT,
    CanonicalSMILES TEXT,
    Title TEXT,
    IUPACName TEXT,
    MonoisotopicMass TEXT,
    IsomericSMILES TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(query_identifier, query_type)
);
CREATE INDEX IF NOT EXISTS idx_cache_inchikey ON cached_molecules(InChIKey);
CREATE INDEX IF NOT EXISTS idx_cache_inchikey14 ON cached_molecules(InChIKey14);
"""
