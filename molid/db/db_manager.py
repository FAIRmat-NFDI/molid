import argparse
import os
import sys
from molid.db.database import initialize_database
from molid.pubchemproc.pubchem import download_and_process_file
from molid.utils.disk_utils import check_disk_space
from molid.utils.ftp_utils import get_total_files_from_ftp, download_file_with_resume

# Configuration
DOWNLOAD_FOLDER = "downloads"
PROCESSED_FOLDER = "processed"
DEFAULT_DATABASE_FILE = "pubchem_data_FULL.db"


def create_database(database_file):
    """Create the SQLite database."""
    fields = {
        "SMILES": "PUBCHEM_SMILES",
        "InChIKey": "PUBCHEM_IUPAC_INCHIKEY",
        "InChI": "PUBCHEM_IUPAC_INCHI",
        "Formula": "PUBCHEM_MOLECULAR_FORMULA"
    }
    initialize_database(database_file, fields)
    print(f"[INFO] Database created: {database_file}")


def update_database(database_file, max_files=None):
    """Update the database with PubChem data."""
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    os.makedirs(PROCESSED_FOLDER, exist_ok=True)

    # Check disk space
    try:
        check_disk_space(40)  # 40 GB minimum space
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return

    # Get available files from the FTP server
    sdf_files = get_total_files_from_ftp()
    if max_files:
        sdf_files = sdf_files[:max_files]

    # Process each file
    for file_name in sdf_files:
        print(f"[INFO] Processing file: {file_name}")
        local_file = download_file_with_resume(file_name, DOWNLOAD_FOLDER)
        if local_file:
            download_and_process_file(file_name, database_file)
        else:
            print(f"[WARNING] Skipping file: {file_name}")


def main():
    """CLI tool for creating, updating, or using a PubChem database."""
    parser = argparse.ArgumentParser(description="Manage the PubChem database for molecular identification.")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Subcommand: create
    create_parser = subparsers.add_parser("create", help="Create a new PubChem database.")
    create_parser.add_argument("--db-file", type=str, default=DEFAULT_DATABASE_FILE, help="Path to the new database file (default: pubchem_data_FULL.db).")

    # Subcommand: update
    update_parser = subparsers.add_parser("update", help="Update an existing PubChem database with new data.")
    update_parser.add_argument(
        "--db-file", type=str, required=True,
        help="Path to the existing database file."
    )
    update_parser.add_argument(
        "--max-files", type=int,
        help="Maximum number of PubChem data files to process during the update."
    )

    # Subcommand: use (open an existing database without modification)
    use_parser = subparsers.add_parser("use", help="Use an existing database for querying without modifying it.")
    use_parser.add_argument(
        "--db-file", type=str, required=True,
        help="Path to the existing database file."
    )

    args = parser.parse_args()

    if args.command == "create":
        create_database(args.db_file)
    elif args.command == "update":
        if os.path.exists(args.db_file):
            update_database(args.db_file, args.max_files)
        else:
            print(f"[ERROR] Database file '{args.db_file}' does not exist. Use 'create' to generate a new database.")
            sys.exit(1)  # Ensure exit on error
    elif args.command == "use":
        if os.path.exists(args.db_file):
            print(f"[INFO] Using existing database: {args.db_file}")
        else:
            print(f"[ERROR] The specified database file '{args.db_file}' does not exist. Please provide a valid database.")
            sys.exit(1)  # Ensure exit on error
    else:
        parser.print_help()
        sys.exit(1)  # Ensure exit when no valid command is given

