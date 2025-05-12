# MolID

MolID is a command-line tool and Python package for downloading, processing, and querying chemical compound data from PubChem. It supports both a full offline SQLite database of PubChem compound dumps and on-demand online fetches with optional per-user caching.

## Features

- **PubChem Data Processing**
  - Download `.sdf.gz` files from NCBI FTP, unpack and extract core properties: SMILES, InChI, InChIKey, formula.
  - Robust resume support and retry logic for large FTP transfers.

- **Database Management**
  - Build and maintain a full offline SQLite database of PubChem compounds (`master_db`).
  - Track processed folders to avoid redundant work.
  - Optional per-user cache (`cache_db`) for online API lookups.

- **Flexible Search Modes**
  - **`offline-basic`**: lookup by full or 14-character InChIKey prefix in the master DB.
  - **`offline-advanced`**: filter by any combination of columns (e.g. `Formula=C6H6,SMILES=c1ccccc1`).
  - **`online-only`**: query the PubChem REST API directly each time.
  - **`online-cached`**: query API and store responses locally; cache lookups for speed.

- **CLI Interface**
  - `update` command to download and ingest PubChem SDFs into the master DB.
  - `search` command to find a molecule by identifier, with configurable ID type.

- **Programmatic API**
  - Python functions to search from raw XYZ content, ASE `Atoms` objects, `.xyz`/`.extxyz`/`.sdf` files, or simple identifiers.
  - Unified entry point: `run(data, config_path)` returns a property dictionary and the data source.

---

## Folder Structure

```
.
├── cli.py                   # Entry-point for update & search CLI
├── run.py                   # Single `run(data, config_path)` API
├── config.yaml              # Default configuration template
├── molid/                   # Main Python package
│   ├── db/                  # Offline & cache database modules
│   │   ├── db_manager.py    # Create/update master SQLite DB & CLI “create/update/use” entrypoints
│   │   ├── schema.py        # SQL schema for offline & cache DBs
│   │   └── db_utils.py      # Schema init & record insertion (offline + cache)
│   ├── pubchem_api/         # PubChem REST API client & cache lookup
│   │   ├── cache.py         # API response caching logic
│   │   ├── fetch.py         # PubChem PUG REST API client
│   │   └── offline.py       # Offline InChIKey / InChIKey14 lookup from master DB
│   ├── pubchemproc/         # PubChem SDF download & processing
│   │   ├── file_handler.py  # Gzip validation, unpack, cleanup
│   │   └── pubchem.py       # Process SDF → property dicts
│   ├── utils/               # Miscellaneous utility modules
│   │   ├── conversion.py    # XYZ/ASE → InChIKey via OpenBabel
│   │   ├── disk_utils.py    # Disk-space checks
│   │   └── ftp_utils.py     # FTP listing & resume-capable download
│   ├── search/              # Core search logic
│   │   ├── db_lookup.py     # Master-DB InChIKey lookup helper
│   │   └── service.py       # SearchService implements all modes (offline/online/cached)
│   └── pipeline.py          # High-level functions: search_identifier, search_from_*
├── requirements.txt         # Python dependencies
├── README.md                # Project documentation
└── LICENSE                  # MIT license

tests/                     # Unit tests
├── test_pubchemproc.py    # PubChem processing tests
├── test_db.py             # Database function tests
└── test_utils.py          # Utility function tests

```

## Installation

```bash
git clone https://github.com/your_org/MolID.git
cd MolID
pip install -r requirements.txt
```

### System Dependencies

OpenBabel is a key dependency for this project and is included in `pyproject.toml` and `requirements.txt` as `openbabel-wheel`, so it should be installed automatically. If for any reason it isn’t, you can manually install it with:
```sh
pip install openbabel-wheel
```
**Note:**
OpenBabel relies on system libraries such as libxrender1 and libxext6. In minimal installations (including Docker containers) these libraries may be missing. If you encounter errors indicating that `libXrender.so.1` or `libXext.so.6` is missing, you’ll need to install these libraries manually (see Installing System Dependencies).

After installing OpenBabel, verify the installation by running:

```sh
obabel -V
```
This command should display the version of Open Babel, confirming that it is installed correctly.

#### Installing System Dependencies

**Debian/Ubuntu:**
```sh
sudo apt-get update
sudo apt-get install libxrender1 libxext6
```

**Fedora/CentOS/RHEL:**
```sh
sudo dnf install libXrender libXext
```

**Arch Linux:**
```sh
sudo pacman -S libxrender libxext
```

**macOS:**
Install XQuartz to provide the necessary X11 libraries.

**Windows:**
If you are running a Linux environment (e.g., via WSL or Cygwin), use the appropriate Linux commands. Otherwise, Windows typically does not require these libraries unless you are running Linux-based tools.


## Configuration

Edit `config.yaml` in the project root:

```yaml
master_db: "pubchem_data_FULL.db"    # Path to the master SQLite DB
cache_db:  "pubchem_cache.db"       # Path to per-user cache DB
mode:      "online-cached"          # offline-basic | offline-advanced | online-only | online-cached
cache_enabled: true                  # Enable writes to cache in online-cached mode
```

## CLI Usage

### 1. Create (or migrate) the master database

```sh
molid update --db-file path/to/master.db --max-files 100
```
- **`--db-file`**: location of the master SQLite.
- **`--max-files`**: limit number of SDFs (for testing).

### 2. Update the master database

```sh
molid update --db-file pubchem_data.db
```
Downloads the latest SDFs and ingests them into `pubchem_data.db`.

### 3. Search for a molecule

```sh
molid search <identifier> [--id-type inchikey|name|smi|...]
```
Example:
```sh
molid search QWERTYUIOPLKJHG --id-type inchikey
```
Prints JSON of properties and the source (offline vs. API).

---

## Programmatic API

```python
from molid.run import run

# Search from raw XYZ string:
xyz_content = open("molecule.xyz").read()
result, source = run(xyz_content, config_path="config.yaml")
print(source, result)

# Or search by identifier:
from molid.pipeline import search_identifier
result, source = search_identifier("aspirin", id_type="name")
```

- **`run(data, config_path)`** automatically detects ASE Atoms, file paths, or raw XYZ strings.
- **`search_from_atoms`**, **`search_from_file`** and **`search_identifier`** are available for finer control.

---

## Development & Testing

- Run the full test suite:
  ```sh
  pytest tests/
  ```
- Linting & formatting:
  ```sh
  black .
  flake8 .
  ```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
