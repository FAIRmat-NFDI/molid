# Molecule Identification Pipeline

This repository contains a molecular identification pipeline for processing PubChem data, extracting chemical structures, and querying a local database using molecular fingerprints.

## Folder Structure
```
molid/ # Main package directory
├── init.py # Marks the folder as a package
├── pubchemproc/ # Contains PubChem processing functions
│ ├── init.py
│ ├── pubchem.py # Functions for downloading and processing PubChem data
│ ├── file_handler.py # File unpacking and validation
│ └── query.py # Query database and CLI tool
├── db/ # Database-related functions
│ ├── init.py
│ ├── database.py # Database initialization and data storage
│ ├── search.py # Search functionality for molecular queries
│ └── db_manager.py # Handles database creation and updates
└── utils/ # Shared utilities
├── init.py
├── ftp_utils.py # FTP-related functions for downloading PubChem data
├── disk_utils.py # Disk space checks and cleanup
└── conversion.py # Conversion of XYZ/Atoms to InChIKey

### Other Files
tests/ # Unit tests
├── test_pubchemproc.py # Tests for PubChem processing functions
├── test_db.py # Tests for database functions
└── test_utils.py # Tests for utility functions

setup.py # Package metadata and installation script
README.md # Documentation for the package
LICENSE # License information
requirements.txt # Dependencies required to run the package
```
---

## Features

- **Download & Process PubChem Data**
  Extracts molecular properties from PubChem `.sdf.gz` files.

- **Database Management**
  Stores extracted molecular fingerprints in an SQLite database for efficient querying.

- **Query System**
  Allows users to search for molecules using **InChIKeys** or **SMILES** notation.

- **CLI Interface**
  Users can interact with the pipeline via a command-line interface.

- **Efficient Storage & Retrieval**
  Uses indexing to speed up searches for molecular data.

---

## Installation

### Prerequisites
Before installing the package, ensure you have:
- A Linux system (tested on Ubuntu 20.04+)
- Python 3.8 or later
- Git installed

### Automatic Installation (Recommended)
To install all dependencies, Open Babel, and Python packages on Linux (Debian/Ubuntu), run:

```sh
./install_dependencies.sh
pip install .
```
Some systems may require sudo privileges; in such cases, use the commented-out lines in
the .sh file instead of the lines without sudo.

For other OS, please determine how to convert the commands in the .sh file to those
compatible with your system. OS-independent support may be provided in the future.

### Manual Installation

If you prefer manual installation, follow the steps in install_dependencies.sh manually.

### Usage

**1️. Create a Database**
To initialize an empty PubChem database:
python -m molid.db_manager create --db-file pubchem_data.db

**2️. Download & Process PubChem Data**
Download and store molecular data:
python -m molid.db_manager update --db-file pubchem_data.db --max-files 10
    --max-files: Specifies how many PubChem .sdf.gz files to process.

**3️. Query the Database**
Search for a molecule using an XYZ structure:
python -m molid.pubchemproc.query example.xyz pubchem_data.db

### Example
Example of using molid in a Python script:
```
from molid import query_pubchem_database

# Define file paths
xyz_file = "path/to/xyz-file"
database_file = "path/to/db-file"

# Run query
inchikey, results = query_pubchem_database(xyz_file, database_file)

# Display results
print(f"InChIKey: {inchikey}")
print("Results:")
for row in results:
    print(row)

```

### Components

**Query System:**
    Uses query.py to extract InChIKey from molecular structures.
    Supports both XYZ files and ase.Atoms objects.
    Queries the local SQLite database for matching records.

**Database Management**
Uses database.py to store molecular fingerprints.
Supports SMILES, InChI, and InChIKey.
Provides fast retrieval using an indexed InChIKey column.

**PubChem Data Processing**
    Uses pubchem.py to download, extract, and process large PubChem datasets.
    Parses .sdf files to extract relevant molecular identifiers.

## Development & Testing

To run tests:
pytest tests/

## License
This project is licensed under the MIT License. See LICENSE for details.
