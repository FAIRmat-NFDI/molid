import os
import sys
import logging
import click
from datetime import datetime, date
from pathlib import Path
import ftplib

from molid.db.db_utils import (
    create_offline_db as init_db,
    save_to_database,
    get_archive_state,
    upsert_archive_state,
)
from molid.pubchemproc.pubchem import unpack_and_process_file
from molid.utils.disk_utils import check_disk_space
from molid.utils.ftp_utils import (
    FTP_SERVER,
    get_changed_sdf_files,
    download_file_with_resume,
    remote_md5_path,
)
from molid.pubchemproc.file_handler import verify_md5, read_expected_md5

logger = logging.getLogger(__name__)

DEFAULT_DOWNLOAD_FOLDER = 'downloads'
DEFAULT_PROCESSED_FOLDER = 'processed'
MAX_CONSECUTIVE_FAILURES = 3

def _get_last_ingested_date(database_file: str) -> date | None:
    """Return the most recent ingestion date stored in processed_archives (UTC)."""
    from molid.db.sqlite_manager import DatabaseManager
    db = DatabaseManager(database_file)
    row = db.query_one(
        "SELECT MAX(last_ingested) AS dt FROM processed_archives WHERE status = 'ingested'",
        []
    )
    if row and row.get("dt"):
        try:
            return datetime.fromisoformat(row["dt"]).date()
        except ValueError:
            pass
    return None

def create_offline_db(db_file: str) -> None:
    """Initialize the offline master database schema."""
    init_db(db_file)

def update_database(
    database_file: str,
    max_files: int = None,
    download_folder: str = DEFAULT_DOWNLOAD_FOLDER,
    processed_folder: str = DEFAULT_PROCESSED_FOLDER,
) -> None:
    """Update the master PubChem database from PubChem FULL snapshot, then Monthly deltas."""
    # Ensure schema exists
    init_db(database_file)
    logger.info("Starting update for DB: %s", database_file)

    # Prepare directories
    os.makedirs(download_folder, exist_ok=True)
    os.makedirs(processed_folder, exist_ok=True)

    # Check disk space (require at least 50 GB free)
    try:
        check_disk_space(50)
    except RuntimeError as e:
        logger.error(f"[ERROR] {e}")
        sys.exit(1)

    # Decide plan: first run -> FULL snapshot; otherwise -> MONTHLY since last ingest
    last_dt = _get_last_ingested_date(database_file)
    logger.info("Connecting to FTP: %s", FTP_SERVER)
    with ftplib.FTP(FTP_SERVER, timeout=60) as ftp:
        ftp.login(user="anonymous", passwd="guest@example.com")
        ftp.set_pasv(True)
        logger.info("Building update plan (since=%s)", last_dt if last_dt else "FULL")
        plan = get_changed_sdf_files(ftp, since=last_dt)
    logger.info("Plan size: %d archives", len(plan))
    if max_files:
        plan = plan[:max_files]
    logger.info(
        "Update plan: %s (%d archives)",
        "FULL snapshot" if last_dt is None else f"MONTHLY since {last_dt.isoformat()}",
        len(plan),
    )

    consecutive_failures = 0
    with click.progressbar(plan, label="Ingesting archives", show_percent=True) as bar:
        for remote_gz, remote_md5, source in plan:
            file_name = Path(remote_gz).name
            try:
                logger.info("Processing: %s (%s)", file_name, source)
                # If we already ingested this archive, compare remote MD5 — skip if unchanged
                state = get_archive_state(database_file, file_name)
                if state and state.get("status") == "ingested":
                    md5_local = download_file_with_resume(remote_md5, download_folder)
                    if not md5_local:
                        logger.warning("Could not fetch MD5 for %s; will re-download anyway.", file_name)
                    else:
                        new_md5 = read_expected_md5(Path(md5_local))
                        if new_md5 and new_md5 == state.get("md5"):
                            logger.info("Upstream MD5 unchanged, skipping: %s", file_name)
                            consecutive_failures = 0
                            continue
                        logger.info("MD5 changed upstream; re-ingesting: %s", file_name)

                # 1) Download .gz and .md5
                logger.debug("Downloading archive: %s", remote_gz)
                local_file = download_file_with_resume(remote_gz, download_folder)
                if not local_file:
                    logger.warning("Download failed: %s", file_name)
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        logger.error("Aborting after %d consecutive failures", MAX_CONSECUTIVE_FAILURES)
                        break
                    continue

                # 2) Download its .md5 companion
                logger.debug("Downloading checksum: %s", remote_md5)
                md5_file = download_file_with_resume(remote_md5, download_folder)
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
                logger.debug("Checksum OK for %s", file_name)
                logger.debug("Unpacking & processing: %s", file_name)
                success = unpack_and_process_file(
                    file_name=file_name,
                    download_folder=download_folder,
                    processed_folder=processed_folder,
                    process_callback=lambda data: save_to_database(
                        database_file,
                        data,
                        list(data[0].keys()) if data else []
                    )
                )

                if success:
                    new_md5 = read_expected_md5(md5_path)
                    upsert_archive_state(
                        database_file,
                        file_name,
                        status="ingested",
                        source=source,
                        md5=new_md5,
                        last_ingested=datetime.utcnow().isoformat(timespec="seconds"),
                        last_error=None,
                    )
                    logger.info("Completed: %s", file_name)
                    consecutive_failures = 0
                else:
                    logger.warning("Processing failed: %s", file_name)
                    upsert_archive_state(
                        database_file, file_name, status="failed",
                        source=source, last_error="processing failed"
                    )
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        logger.error("Aborting after %d consecutive failures", MAX_CONSECUTIVE_FAILURES)
                        break

            except Exception as e:
                logger.error(f"[ERROR] Exception processing {file_name}: {e}")
                upsert_archive_state(
                    database_file, file_name, status="failed",
                    source=source, last_error=str(e)
                )
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
