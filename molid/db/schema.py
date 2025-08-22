"""
Centralized SQL schema definitions for MolID's SQLite databases.
"""

OFFLINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS compound_data (
    CID                 INTEGER PRIMARY KEY,
    Name                TEXT,
    IUPACName           TEXT,
    Formula             TEXT,
    ExactMass           TEXT,
    MolecularWeight     REAL,
    MonoisotopicMass    REAL,
    SMILES              TEXT,
    InChIKey            TEXT,
    InChI               TEXT
);
CREATE INDEX IF NOT EXISTS idx_inchikey ON compound_data(InChIKey);
CREATE INDEX IF NOT EXISTS idx_compound_inchikey14 ON compound_data(substr(InChIKey, 1, 14));

CREATE TABLE IF NOT EXISTS processed_archives (
    archive_name   TEXT PRIMARY KEY,
    status         TEXT,
    last_error     TEXT,
    md5            TEXT,
    source         TEXT NOT NULL,          -- 'full' or 'monthly'
    last_ingested  TIMESTAMP,              -- ISO string in UTC
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cached_molecules (
    CID                INTEGER PRIMARY KEY,
    InChIKey           TEXT UNIQUE,
    MolecularFormula   TEXT,
    InChI              TEXT,
    TPSA               REAL,
    Charge             INTEGER,
    ConnectivitySMILES TEXT,
    Title              TEXT,
    IUPACName          TEXT,
    XLogP              REAL,
    ExactMass          REAL,
    Complexity         INTEGER,
    MonoisotopicMass   TEXT,
    SMILES     TEXT,
    fetched_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cache_inchikey ON cached_molecules(InChIKey);
"""
