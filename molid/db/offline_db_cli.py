import argparse
import os
import sys
import traceback
import logging

from molid.db.db_utils import (
    create_offline_db,
    save_to_database,
    is_folder_processed,
    mark_folder_as_processed,
)
from molid.pubchemproc.pubchem import (
    download_and_process_file,
    FIELDS_TO_EXTRACT,
)
from molid.utils.disk_utils import check_disk_space
from molid.utils.ftp_utils import (
    get_total_files_from_ftp,
    download_file_with_resume,
)

logger = logging.getLogger(__name__)

# Default directories and filenames
DOWNLOAD_FOLDER = "downloads"
PROCESSED_FOLDER = "processed"
DEFAULT_DATABASE_FILE = "pubchem_data_FULL.db"
MAX_CONSECUTIVE_FAILURES = 3


def update_database(
    database_file: str,
    max_files: int = None,
    download_folder: str = DOWNLOAD_FOLDER,
    processed_folder: str = PROCESSED_FOLDER,
):
    """Update the master PubChem database by downloading and processing SDF files."""
    # 0) Ensure schema exists
    create_offline_db(database_file)

    # 1) Prepare folders
    os.makedirs(download_folder, exist_ok=True)
    os.makedirs(processed_folder, exist_ok=True)

    # 2) Check for sufficient disk space
    try:
        check_disk_space(50)  # require at least 50 GB free
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return

    # 3) List available FTP files
    sdf_files = get_total_files_from_ftp()
    if max_files:
        sdf_files = sdf_files[:max_files]

    consecutive_failures = 0
    # 4) Process each file with robust error handling
    for file_name in sdf_files:
        try:
            # Skip if already processed
            if is_folder_processed(database_file, file_name):
                logger.info("Skipping already-processed folder: %s", file_name)
                consecutive_failures = 0
                continue

            logger.info("Processing file: %s", file_name)
            local_file = download_file_with_resume(file_name, download_folder)
            if not local_file:
                logger.warning("Download failed, skipping: %s", file_name)
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error("%d consecutive failures, aborting.", MAX_CONSECUTIVE_FAILURES)
                    break
                continue

            # Process and save
            success = download_and_process_file(
                file_name=file_name,
                download_folder=download_folder,
                processed_folder=processed_folder,
                fields_to_extract=FIELDS_TO_EXTRACT,
                process_callback=lambda data: save_to_database(
                    database_file,
                    data,
                    list(data[0].keys()) if data else []
                )
            )

            if success:
                mark_folder_as_processed(database_file, file_name)
                logger.info("Completed and marked: %s", file_name)
                consecutive_failures = 0
            else:
                logger.warning("Processing failed for: %s", file_name)
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error("%d consecutive failures, aborting.", MAX_CONSECUTIVE_FAILURES)
                    break

        except Exception as e:
            print(f"[ERROR] Exception processing {file_name}: {e}")
            traceback.print_exc()
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"[ERROR] {MAX_CONSECUTIVE_FAILURES} consecutive exceptions, aborting.")
                break


def main():
    parser = argparse.ArgumentParser(
        description="Manage the PubChem database for molecular identification."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create
    create_p = subparsers.add_parser("create", help="Create a new PubChem database.")
    create_p.add_argument(
        "--db-file",
        type=str,
        default=DEFAULT_DATABASE_FILE,
        help="Path to the new database file (default: pubchem_data_FULL.db)."
    )

    # update
    update_p = subparsers.add_parser("update", help="Update an existing PubChem database.")
    update_p.add_argument(
        "--db-file",
        type=str,
        required=True,
        help="Path to the existing database file."
    )
    update_p.add_argument(
        "--max-files",
        type=int,
        help="Max number of PubChem SDF files to process."
    )
    update_p.add_argument(
        "--download-folder",
        type=str,
        default=DOWNLOAD_FOLDER,
        help="Directory to store downloaded .gz files."
    )
    update_p.add_argument(
        "--processed-folder",
        type=str,
        default=PROCESSED_FOLDER,
        help="Directory to unpack and process SDF files."
    )

    # use (just verify existence)
    use_p = subparsers.add_parser("use", help="Use an existing database for queries.")
    use_p.add_argument(
        "--db-file",
        type=str,
        required=True,
        help="Path to the existing database file."
    )

    args = parser.parse_args()

    if args.command == "create":
        create_offline_db(args.db_file)

    elif args.command == "update":
        if os.path.exists(args.db_file):
            update_database(
                args.db_file,
                max_files=args.max_files,
                download_folder=args.download_folder,
                processed_folder=args.processed_folder,
            )
        else:
            logger.error("Database file '%s' does not exist. Use 'create'.", args.db_file)
            sys.exit(1)

    elif args.command == "use":
        if os.path.exists(args.db_file):
            logger.info("Using existing database: %s", args.db_file)
        else:
            logger.error("Database '%s' not found.", args.db_file)
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
