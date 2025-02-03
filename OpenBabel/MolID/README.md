======================================================================
Folder Structure
======================================================================
molid/
├── molid/                       # Main package folder
│   ├── __init__.py              # Makes the folder a package
│   ├── pubchemproc/               # PubChem processing functions
│   │   ├── __init__.py
│   │   ├── pubchem.py           # Functions for downloading and processing PubChem data
│   │   ├── file_handler.py      # File unpacking and validation
│   ├── db/                      # Database-related functions
│   │   ├── __init__.py
│   │   ├── database.py          # DB initialization and queries
│   │   ├── search.py            # Search functionality for XYZ files
│   ├── utils/                   # Shared utilities
│   │   ├── __init__.py
│   │   ├── ftp_utils.py         # FTP-related functions
│   │   ├── disk_utils.py        # Disk space checks and cleanup
├── tests/                       # Unit tests for the package
│   ├── test_pubchemproc.py        # Tests for processing functions
│   ├── test_db.py               # Tests for database functions
│   ├── test_utils.py            # Tests for utility functions
├── setup.py                     # Package metadata and installation script
├── README.md                    # Package documentation
├── LICENSE                      # License file
└── requirements.txt             # Dependencies for the package