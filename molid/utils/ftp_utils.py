from __future__ import annotations

import ftplib
import time
import logging
import socket
from pathlib import Path

from molid.pubchemproc.file_handler import (
    validate_gz_file,
    GzipValidationError,
)

logger = logging.getLogger(__name__)

FTP_SERVER = "ftp.ncbi.nlm.nih.gov"
FTP_DIRECTORY = "/pubchem/Compound/CURRENT-Full/SDF/"


def validate_start_position(local_file_path: Path, ftp_size: int) -> int:
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


def get_total_files_from_ftp() -> list[str]:
    """Fetch the list of available files on the FTP server."""
    try:
        with ftplib.FTP(FTP_SERVER, timeout=30) as ftp:
            ftp.login(user="anonymous", passwd="guest@example.com")
            ftp.set_pasv(True)
            ftp.cwd(FTP_DIRECTORY)
            files: list[str] = []
            ftp.retrlines("NLST", lambda x: files.append(x))
            sdf_files = [f for f in files if f.endswith(".sdf.gz")]
            logger.info("Total .sdf.gz files available on server: %d", len(sdf_files))
            return sdf_files
    except socket.gaierror as dns_err:
        logger.error("DNS resolution failed for FTP server %s: %s", FTP_SERVER, dns_err)
        raise RuntimeError(f"DNS resolution failed for FTP server {FTP_SERVER}: {dns_err}")
    except Exception as e:
        raise RuntimeError(f"Failed to fetch file list from FTP server: {e}")


def attempt_download(
    file_name: str,
    local_file_path: Path,
    start_position: int,
    ftp: ftplib.FTP,
) -> bool:
    """Attempt to download a file with resume or restart logic."""
    ftp.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    ftp_size = ftp.size(file_name)
    mode = "ab" if start_position > 0 else "wb"
    with open(local_file_path, mode) as local_file:
        try:
            # Use smaller blocksize for more reliable transfers
            ftp.retrbinary(
                f"RETR {file_name}",
                local_file.write,
                blocksize=1024,
                rest=start_position or None,
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
    logger.error("File size mismatch for %s (got %d vs %d).", file_name, local_file_path.stat().st_size, ftp_size)
    return False


def download_via_http(file_name: str, download_folder: str) -> Path:
    """Fallback download via HTTPS with resume support."""
    try:
        import requests
    except ImportError:
        raise RuntimeError("requests library required for HTTP fallback but is not installed.")

    url = f"https://{FTP_SERVER}{FTP_DIRECTORY}{file_name}"
    local = Path(download_folder) / file_name
    headers: dict[str, str] = {}
    if local.exists():
        headers["Range"] = f"bytes={local.stat().st_size}-"
        logger.debug("Resuming HTTP download for %s from byte %d", file_name, local.stat().st_size)

    with requests.get(url, stream=True, headers=headers, timeout=600) as r:
        r.raise_for_status()
        mode = "ab" if "Range" in headers else "wb"
        with open(local, mode) as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    logger.info("Successfully downloaded via HTTP: %s", file_name)
    return local

def download_file_with_resume(
    file_name: str,
    download_folder: str,
    max_retries: int = 5,
) -> Path | None:
    """Download a file with resume support, retry logic, and HTTPS fallback."""
    local_file_path = Path(download_folder) / file_name
    backoff = 5

    for attempt in range(1, max_retries + 1):
        try:
            with ftplib.FTP(FTP_SERVER, timeout=600) as ftp:
                ftp.set_pasv(True)
                ftp.login(user="anonymous", passwd="guest@example.com")
                ftp.cwd(FTP_DIRECTORY)

                ftp_size = ftp.size(file_name)
                logger.debug(
                    "Server-reported file size for %s: %d", file_name, ftp_size
                    )

                start_position = validate_start_position(local_file_path, ftp_size)
                if attempt_download(file_name, local_file_path, start_position, ftp):
                    return local_file_path

        except socket.gaierror as dns_err:
            logger.error(
                "Name resolution error on attempt %d for %s: %s",
                attempt,
                file_name,
                dns_err
            )
            try:
                logger.info(
                    "Falling back to HTTPS due to DNS error: %s",
                    file_name
                )
                return download_via_http(file_name, download_folder)
            except Exception as http_e:
                logger.error(
                    "HTTPS fallback failed after DNS error: %s",
                    http_e
                )
                return None
        except Exception as e:
            logger.error(
                "Attempt %d/%d failed for %s: %s",
                attempt,
                max_retries,
                file_name,
                e
            )
            if local_file_path.exists():
                logger.warning(
                    "Deleting incomplete file: %s",
                    local_file_path
                )
                local_file_path.unlink()
            if attempt == max_retries:
                logger.info(
                    "Max retries reached for %s, falling back to HTTP",
                    file_name
                )
                try:
                    return download_via_http(file_name, download_folder)
                except Exception as http_e:
                    logger.error(
                        "HTTPS fallback failed: %s",
                        http_e
                    )
                    return None
        time.sleep(backoff)
        backoff *= 2

    logger.error(
        "Failed to download %s after %d attempts.",
        file_name,
        max_retries
    )
    if local_file_path.exists():
        local_file_path.unlink()
    return None
