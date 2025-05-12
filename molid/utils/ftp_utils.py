import ftplib
import time
import logging
from pathlib import Path
from molid.pubchemproc.file_handler import (
    validate_gz_file,
    GzipValidationError,
)

logger = logging.getLogger(__name__)

FTP_SERVER = "ftp.ncbi.nlm.nih.gov"
FTP_DIRECTORY = "/pubchem/Compound/CURRENT-Full/SDF/"


def validate_start_position(local_file_path, ftp_size):
    """Validate the start position for resuming a download."""
    start_position = 0
    if local_file_path.exists():
        try:
            validate_gz_file(local_file_path)
        except GzipValidationError:
            logger.warning("Invalid partial file %s. Restarting download.", local_file_path.name)
            local_file_path.unlink()
            return 0
        start_position = local_file_path.stat().st_size
        logger.debug("Resuming download for %s from byte %d", local_file_path.name, start_position)

    if start_position > ftp_size:
        logger.error("Start position %d exceeds file size %d. Restarting.", start_position, ftp_size)
        local_file_path.unlink()
        return 0

    return start_position


def get_total_files_from_ftp():
    """Fetch the list of available files on the FTP server."""
    try:
        with ftplib.FTP(FTP_SERVER) as ftp:
            ftp.login(user="anonymous", passwd="guest@example.com")
            ftp.cwd(FTP_DIRECTORY)
            files = []
            ftp.retrlines("LIST", lambda x: files.append(x.split()[-1]))
            sdf_files = [f for f in files if f.endswith(".sdf.gz")]
            logger.info("Total .sdf.gz files available on server: %d", len(sdf_files))
            return sdf_files
    except Exception as e:
        raise RuntimeError(f"Failed to fetch file list from FTP server: {e}")


def attempt_download(file_name, local_file_path, start_position, ftp):
    """Attempt to download a file with resume or restart logic."""
    ftp_size = ftp.size(file_name)
    with open(local_file_path, "ab" if start_position > 0 else "wb") as local_file:
        try:
            ftp.retrbinary(
                f"RETR {file_name}",
                local_file.write,
                rest=start_position if start_position > 0 else None
            )
        except ftplib.error_perm as e:
            if "REST" in str(e):
                logger.warning("Server does not support REST. Restarting download for %s.", file_name)
                local_file.truncate(0)
                ftp.retrbinary(f"RETR {file_name}", local_file.write)
            else:
                raise

    if local_file_path.stat().st_size == ftp_size:
        logger.info("Successfully downloaded: %s", file_name)
        return True
    else:
        logger.error("File size mismatch for %s. Retrying...", file_name)
        return False


def download_file_with_resume(file_name, download_folder, max_retries=5):
    """Download a file with resume support and retry logic."""
    local_file_path = Path(download_folder) / file_name
    backoff = 5

    for attempt in range(1, max_retries + 1):
        try:
            with ftplib.FTP(FTP_SERVER, timeout=600) as ftp:
                ftp.set_pasv(True)
                ftp.login(user="anonymous", passwd="guest@example.com")
                ftp.cwd(FTP_DIRECTORY)

                ftp_size = ftp.size(file_name)
                logger.debug("Server-reported file size for %s: %d", file_name, ftp_size)

                start_position = validate_start_position(local_file_path, ftp_size)

                if attempt_download(file_name, local_file_path, start_position, ftp):
                    return local_file_path

        except Exception as e:
            logger.error("Attempt %d/%d failed for %s: %s", attempt, max_retries, file_name, e)
            if local_file_path.exists():
                logger.warning("Deleting incomplete file: %s", local_file_path)
                local_file_path.unlink()
            time.sleep(backoff)
            backoff *= 2

    logger.error("Failed to download %s after %d attempts.", file_name, max_retries)
    if local_file_path.exists():
        local_file_path.unlink()
    return None
