import os
import sys
import logging
from pathlib import Path

from molid.db.db_utils import (
    create_offline_db as init_db,
    save_to_database,
    is_folder_processed,
    mark_folder_as_processed,
)
from molid.pubchemproc.pubchem import download_and_process_file, FIELDS_TO_EXTRACT
from molid.utils.disk_utils import check_disk_space
from molid.utils.ftp_utils import get_total_files_from_ftp, download_file_with_resume
from molid.pubchemproc.file_handler import verify_md5

logger = logging.getLogger(__name__)

DEFAULT_DOWNLOAD_FOLDER = 'downloads'
DEFAULT_PROCESSED_FOLDER = 'processed'
MAX_CONSECUTIVE_FAILURES = 3

def create_offline_db(db_file: str) -> None:
    """Initialize the offline master database schema."""
    init_db(db_file)

def update_database(
    database_file: str,
    max_files: int = None,
    download_folder: str = DEFAULT_DOWNLOAD_FOLDER,
    processed_folder: str = DEFAULT_PROCESSED_FOLDER,
) -> None:
    """Update the master PubChem database by downloading and processing SDF files."""
    # Ensure schema exists
    init_db(database_file)

    # Prepare directories
    os.makedirs(download_folder, exist_ok=True)
    os.makedirs(processed_folder, exist_ok=True)

    # Check disk space (require at least 50 GB free)
    try:
        check_disk_space(50)
    except RuntimeError as e:
        logger.error(f"[ERROR] {e}")
        sys.exit(1)

    # List and optionally limit files
    sdf_files = get_total_files_from_ftp()
    if max_files:
        sdf_files = sdf_files[:max_files]

    consecutive_failures = 0
    for file_name in sdf_files:
        try:
            if is_folder_processed(database_file, file_name):
                logger.info("Skipping already processed folder: %s", file_name)
                consecutive_failures = 0
                continue

            logger.info("Processing file: %s", file_name)

            # 1) Download the .gz
            local_file = download_file_with_resume(file_name, download_folder)
            if not local_file:
                logger.warning("Download failed: %s", file_name)
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error("Aborting after %d consecutive failures", MAX_CONSECUTIVE_FAILURES)
                    break
                continue

            # 2) Download its .md5 companion
            md5_name = f"{file_name}.md5"
            md5_file = download_file_with_resume(md5_name, download_folder)
            if not md5_file:
                logger.warning("Could not fetch MD5 for %s", file_name)
                consecutive_failures += 1
                continue

            # 3) Verify the checksum
            gz_path  = Path(local_file)
            md5_path = Path(md5_file)
            if not verify_md5(gz_path, md5_path):
                # corrupted download: remove and retry
                logger.warning("Bad checksum for %s, will retry downloading.", file_name)
                for p in (gz_path, md5_path):
                    if p.exists():
                        p.unlink()
                consecutive_failures += 1
                continue

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
                logger.info("Completed: %s", file_name)
                consecutive_failures = 0
            else:
                logger.warning("Processing failed: %s", file_name)
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error("Aborting after %d consecutive failures", MAX_CONSECUTIVE_FAILURES)
                    break

        except Exception as e:
            logger.error(f"[ERROR] Exception processing {file_name}: {e}")
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error("Aborting after %d consecutive exceptions", MAX_CONSECUTIVE_FAILURES)
                break

def use_database(db_file: str) -> None:
    """Verify an existing database file is present."""
    if not os.path.exists(db_file):
        logger.error("Database file '%s' not found.", db_file)
        sys.exit(1)
    logger.info("Using database: %s", db_file)
