import os
import sys
import logging
import ftplib
from datetime import datetime, date
from pathlib import Path
from typing import Iterable, Optional, Tuple

import click

from molid.db.db_utils import (
    create_offline_db,
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
)
from molid.pubchemproc.file_handler import verify_md5, read_expected_md5
from molid.db.cas_enrich import enrich_cas_for_cids

logger = logging.getLogger(__name__)

DEFAULT_DOWNLOAD_FOLDER = "downloads"
DEFAULT_PROCESSED_FOLDER = "processed"
MAX_CONSECUTIVE_FAILURES = 3
MIN_FREE_GB = 50

# ---------------------------------------------------------------------------
# Small, focused helpers (unit-test friendly)
# ---------------------------------------------------------------------------

def _get_last_ingested_date(database_file: str) -> Optional[date]:
    """Return the most recent ingestion date stored in processed_archives (UTC)."""
    from molid.db.sqlite_manager import DatabaseManager

    db = DatabaseManager(database_file)
    row = db.query_one(
        "SELECT MAX(last_ingested) AS dt FROM processed_archives WHERE status = 'ingested'",
        [],
    )
    if row and row.get("dt"):
        try:
            return datetime.fromisoformat(row["dt"]).date()
        except ValueError:
            return None
    return None


def _prepare_environment(
    database_file: str,
    download_folder: str,
    processed_folder: str,
    min_free_gb: int = MIN_FREE_GB,
) -> None:
    """Ensure DB schema exists, folders are present, and disk space is sufficient."""
    create_offline_db(database_file)
    os.makedirs(download_folder, exist_ok=True)
    os.makedirs(processed_folder, exist_ok=True)
    check_disk_space(min_free_gb)


def _connect_ftp(server: str = FTP_SERVER) -> ftplib.FTP:
    """Create a logged-in passive FTP connection."""
    ftp = ftplib.FTP(server, timeout=60)
    ftp.login(user="anonymous", passwd="guest@example.com")
    ftp.set_pasv(True)
    return ftp


def _build_update_plan(last_dt: Optional[date], max_files: Optional[int]) -> list[Tuple[str, str, str]]:
    """Return a list of (remote_gz, remote_md5, source) to ingest."""
    logger.info("Connecting to FTP: %s", FTP_SERVER)
    with _connect_ftp() as ftp:
        logger.info("Building update plan (since=%s)", last_dt if last_dt else "FULL")
        plan = get_changed_sdf_files(ftp, since=last_dt)
    if max_files:
        plan = plan[: max_files]
    logger.info(
        "Update plan: %s (%d archives)",
        "FULL snapshot" if last_dt is None else f"MONTHLY since {last_dt.isoformat()}",
        len(plan),
    )
    return plan


def _download_pair(
    remote_gz: str, remote_md5: str, download_folder: str
) -> Tuple[Optional[Path], Optional[Path]]:
    """Download the .gz and its .md5; return local paths (or None on failure)."""
    logger.debug("Downloading archive: %s", remote_gz)
    local_file = download_file_with_resume(remote_gz, download_folder)
    if not local_file:
        logger.warning("Download failed: %s", Path(remote_gz).name)
        return None, None

    logger.debug("Downloading checksum: %s", remote_md5)
    md5_file = download_file_with_resume(remote_md5, download_folder)
    if not md5_file:
        logger.warning("Could not fetch MD5 for %s", Path(remote_gz).name)
        return Path(local_file), None

    return Path(local_file), Path(md5_file)


def _verify_checksum(gz_path: Path, md5_path: Optional[Path]) -> bool:
    """Verify checksum if md5 is present. If absent, treat as failure (strict)."""
    if md5_path is None:
        return False
    if not verify_md5(gz_path, md5_path):
        logger.warning("Bad checksum for %s, will retry downloading.", gz_path.name)
        for p in (gz_path, md5_path):
            try:
                if p and p.exists():
                    p.unlink()
            except Exception:
                logger.debug("Could not remove corrupt file: %s", p)
        return False
    logger.debug("Checksum OK for %s", gz_path.name)
    return True


def _already_ingested_and_unchanged(
    database_file: str, file_name: str, remote_md5_url: str, download_folder: str
) -> bool:
    """Return True if archive was previously ingested and upstream MD5 is unchanged."""
    state = get_archive_state(database_file, file_name)
    if not (state and state.get("status") == "ingested"):
        return False

    md5_local = download_file_with_resume(remote_md5_url, download_folder)
    if not md5_local:
        logger.warning("Could not fetch MD5 for %s; will re-download anyway.", file_name)
        return False

    new_md5 = read_expected_md5(Path(md5_local))
    if new_md5 and new_md5 == state.get("md5"):
        logger.info("Upstream MD5 unchanged, skipping: %s", file_name)
        return True

    logger.info("MD5 changed upstream; re-ingesting: %s", file_name)
    return False


def _ingest(
    database_file: str,
    file_name: str,
    download_folder: str,
    processed_folder: str,
) -> bool:
    """Unpack, process, and persist one archive. Returns success flag."""
    return unpack_and_process_file(
        file_name=file_name,
        download_folder=download_folder,
        processed_folder=processed_folder,
        process_callback=lambda data: save_to_database(
            database_file, data, list(data[0].keys()) if data else []
        ),
    )


def _record_success(
    database_file: str,
    file_name: str,
    md5_path: Optional[Path],
    source: str,
) -> None:
    new_md5 = read_expected_md5(md5_path) if md5_path else None
    upsert_archive_state(
        database_file,
        file_name,
        status="ingested",
        source=source,
        md5=new_md5,
        last_ingested=datetime.utcnow().isoformat(timespec="seconds"),
        last_error=None,
    )
    # best-effort cleanup
    try:
        if md5_path and md5_path.exists():
            md5_path.unlink()
    except Exception:
        logger.debug("Could not remove md5 file: %s", md5_path)


def _record_failure(
    database_file: str, file_name: str, source: str, error: Optional[str] = None
) -> None:
    upsert_archive_state(
        database_file,
        file_name,
        status="failed",
        source=source,
        last_error=(error or "processing failed"),
    )


def _process_single_archive(
    database_file: str,
    item: tuple[str, str, str],
    download_folder: str,
    processed_folder: str,
) -> bool:
    """Process one (remote_gz, remote_md5, source) tuple and return success flag."""
    remote_gz, remote_md5, source = item
    file_name = Path(remote_gz).name

    if _already_ingested_and_unchanged(database_file, file_name, remote_md5, download_folder):
        logger.info("Skipped (unchanged): %s", file_name)
        return True

    gz_path, md5_path = _download_pair(remote_gz, remote_md5, download_folder)
    if not gz_path:
        _record_failure(database_file, file_name, source, "download failed")
        return False

    if not _verify_checksum(gz_path, md5_path):
        _record_failure(database_file, file_name, source, "checksum failed")
        return False

    ok = _ingest(database_file, file_name, download_folder, processed_folder)
    if ok:
        _record_success(database_file, file_name, md5_path, source)
        logger.info("Completed: %s", file_name)
        return True

    _record_failure(database_file, file_name, source)
    logger.warning("Processing failed: %s", file_name)
    return False


def _process_update_plan(
    database_file: str,
    plan: list[tuple[str, str, str]],
    download_folder: str,
    processed_folder: str,
    max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
) -> tuple[int, int]:
    """Run the ingest loop with failure backoff. Returns (successes, failures)."""
    successes = failures = 0
    consecutive_failures = 0

    with click.progressbar(plan, label="Ingesting archives", show_percent=True) as bar:
        for item in bar:
            try:
                ok = _process_single_archive(
                    database_file, item, download_folder, processed_folder
                )
                if ok:
                    successes += 1
                    consecutive_failures = 0
                else:
                    failures += 1
                    consecutive_failures += 1
            except Exception as e:
                remote_gz = Path(item[0]).name
                logger.error("[ERROR] Exception processing %s: %s", remote_gz, e)
                _record_failure(database_file, remote_gz, item[2], str(e))
                failures += 1
                consecutive_failures += 1

            if consecutive_failures >= max_consecutive_failures:
                logger.error(
                    "Aborting after %d consecutive failures", max_consecutive_failures
                )
                break

    return successes, failures


def update_database(
    database_file: str,
    max_files: Optional[int] = None,
    download_folder: str = DEFAULT_DOWNLOAD_FOLDER,
    processed_folder: str = DEFAULT_PROCESSED_FOLDER,
) -> tuple[int, int]:
    """Update DB in three compact steps and return (successes, failures)."""
    logger.info("Starting update for DB: %s", database_file)
    _prepare_environment(database_file, download_folder, processed_folder, MIN_FREE_GB)
    last_dt = _get_last_ingested_date(database_file)
    plan = _build_update_plan(last_dt, max_files)
    successes, failures = _process_update_plan(
        database_file, plan, download_folder, processed_folder
    )
    logger.info("Update finished — %d succeeded, %d failed", successes, failures)
    return successes, failures


def use_database(db_file: str) -> None:
    """Verify an existing database file is present."""
    if not os.path.exists(db_file):
        logger.error("Database file '%s' not found.", db_file)
        sys.exit(1)
    logger.info("Using database: %s", db_file)


def enrich_cas_database(
    database_file: str,
    from_cid: Optional[int] = None,
    limit: Optional[int] = None,
    use_synonyms: bool = False,
    sleep_s: float = 0.2,
    timeout_s: float = 30.0,
    retries: int = 3,
) -> None:
    """Enrich cas_mapping for a slice of CIDs from compound_data."""
    from molid.db.sqlite_manager import DatabaseManager

    db = DatabaseManager(database_file)
    where = "WHERE CID >= ?" if from_cid is not None else ""
    params = [from_cid] if from_cid is not None else []
    lim = f"LIMIT {int(limit)}" if limit else ""
    rows = db.query_all(
        f"SELECT CID FROM compound_data {where} ORDER BY CID {lim}", params
    )
    cids = [r["CID"] for r in rows]
    if not cids:
        logger.info("No CIDs to enrich.")
        return

    logger.info("Enriching CAS for %d CIDs (use_synonyms=%s)", len(cids), use_synonyms)
    added = enrich_cas_for_cids(
        database_file,
        cids,
        sleep_s=sleep_s,
        use_synonyms=use_synonyms,
        timeout_s=timeout_s,
        retries=retries,
    )
    logger.info("CAS enrichment complete: %d (CAS,CID) rows inserted.", added)
