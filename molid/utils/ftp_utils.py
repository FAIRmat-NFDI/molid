from __future__ import annotations

import ftplib
import time
import logging
import socket
import re
from datetime import date
from pathlib import Path

from molid.pubchemproc.file_handler import (
    validate_gz_file,
    GzipValidationError,
)

logger = logging.getLogger(__name__)

FTP_SERVER = "ftp.ncbi.nlm.nih.gov"
PUBCHEM_COMPOUND = "/pubchem/Compound"
FULL_SDF_DIR = f"{PUBCHEM_COMPOUND}/CURRENT-Full/SDF"
MONTHLY_DIR = f"{PUBCHEM_COMPOUND}/Monthly"
FTP_DIRECTORY = "/pubchem/Compound/CURRENT-Full/SDF/"


def validate_start_position(local_file_path: Path, ftp_size: int) -> int:
    """Validate the start position for resuming a download."""
    start_position = 0
    if local_file_path.exists():
        try:
            validate_gz_file(local_file_path)
        except GzipValidationError:
            logger.warning(
                "Invalid partial file %s. Restarting download.", local_file_path.name
            )
            local_file_path.unlink()
            return 0
        start_position = local_file_path.stat().st_size
        logger.debug(
            "Resuming download for %s from byte %d",
            local_file_path.name,
            start_position,
        )

    if start_position > ftp_size:
        logger.error(
            "Start position %d exceeds file size %d. Restarting.",
            start_position,
            ftp_size,
        )
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
        raise RuntimeError(
            f"DNS resolution failed for FTP server {FTP_SERVER}: {dns_err}"
        )
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
                logger.warning(
                    "Server does not support REST. Restarting download for %s.",
                    file_name,
                )
                local_file.truncate(0)
                ftp.retrbinary(f"RETR {file_name}", local_file.write)
            else:
                raise

    if local_file_path.stat().st_size == ftp_size:
        logger.info("Successfully downloaded: %s", file_name)
        return True
    logger.error(
        "File size mismatch for %s (got %d vs %d).",
        file_name,
        local_file_path.stat().st_size,
        ftp_size,
    )
    return False


def download_via_http(remote_path: str, download_folder: str) -> Path:
    """Fallback download via HTTPS with resume support. Accepts absolute remote paths."""
    try:
        import requests
    except ImportError:
        raise RuntimeError(
            "requests library required for HTTP fallback but is not installed."
        )

    url = f"https://{FTP_SERVER}{remote_path}"
    local = Path(download_folder) / Path(remote_path).name
    headers: dict[str, str] = {}
    if local.exists():
        headers["Range"] = f"bytes={local.stat().st_size}-"
        logger.debug(
            "Resuming HTTP download for %s from byte %d",
            local.name,
            local.stat().st_size,
        )

    with requests.get(url, stream=True, headers=headers, timeout=600) as r:
        r.raise_for_status()
        mode = "ab" if "Range" in headers else "wb"
        with open(local, mode) as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    logger.info("Successfully downloaded via HTTP: %s", local.name)
    return local


def download_file_with_resume(
    remote_path: str,
    download_folder: str,
    max_retries: int = 5,
) -> Path | None:
    """Download a file (by absolute remote path) with resume + retries + HTTPS fallback."""
    # Accept both absolute and legacy short names; map short names into FULL_SDF_DIR
    if "/" not in remote_path:
        remote_path = f"{FULL_SDF_DIR}/{remote_path}"
    local_file_path = Path(download_folder) / Path(remote_path).name
    backoff = 5

    for attempt in range(1, max_retries + 1):
        try:
            with ftplib.FTP(FTP_SERVER, timeout=600) as ftp:
                ftp.set_pasv(True)
                ftp.login(user="anonymous", passwd="guest@example.com")
                # cd into the remote directory of the file
                remote_dir = str(Path(remote_path).parent)
                remote_name = Path(remote_path).name
                ftp.cwd(remote_dir)
                ftp_size = ftp.size(remote_name)
                logger.debug(
                    "Server-reported file size for %s: %d", remote_name, ftp_size
                )

                start_position = validate_start_position(local_file_path, ftp_size)
                if attempt_download(remote_name, local_file_path, start_position, ftp):
                    return local_file_path

        except socket.gaierror as dns_err:
            logger.error(
                "Name resolution error on attempt %d for %s: %s",
                attempt,
                remote_path,
                dns_err,
            )
            try:
                logger.info("Falling back to HTTPS due to DNS error: %s", remote_path)
                return download_via_http(remote_path, download_folder)
            except Exception as http_e:
                logger.error("HTTPS fallback failed after DNS error: %s", http_e)
                return None
        except Exception as e:
            logger.error(
                "Attempt %d/%d failed for %s: %s", attempt, max_retries, remote_path, e
            )
            if local_file_path.exists():
                logger.warning("Deleting incomplete file: %s", local_file_path)
                local_file_path.unlink()
            if attempt == max_retries:
                logger.info(
                    "Max retries reached for %s, falling back to HTTP", remote_path
                )
                try:
                    return download_via_http(remote_path, download_folder)
                except Exception as http_e:
                    logger.error("HTTPS fallback failed: %s", http_e)
                    return None
        time.sleep(backoff)
        backoff *= 2

    logger.error("Failed to download %s after %d attempts.", remote_path, max_retries)
    if local_file_path.exists():
        local_file_path.unlink()
    return None


def _safe_mlsd(ftp: ftplib.FTP, path: str) -> list[tuple[str, dict]]:
    """Return MLSD listings if supported; otherwise fall back to NLST names only."""
    try:
        return list(ftp.mlsd(path))
    except (ftplib.error_perm, AttributeError):
        names = ftp.nlst(path)
        return [(n.split("/")[-1], {"type": "file"}) for n in names]


def list_full_sdf_archives(ftp: ftplib.FTP) -> list[str]:
    """List *.sdf.gz in CURRENT-Full/SDF."""
    entries = _safe_mlsd(ftp, FULL_SDF_DIR)
    gz = [name for name, facts in entries if name.endswith(".sdf.gz")]
    gz.sort()
    return [f"{FULL_SDF_DIR}/{name}" for name in gz]


_MONTH_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")  # accept YYYY-MM or YYYY-MM-DD


def list_monthly_sdf_archives_since(ftp: ftplib.FTP, since: date) -> list[str]:
    """
    List *.sdf.gz in Monthly/YYYY-MM[/SDF] (or Monthly/YYYY-MM-DD/SDF) for months >= since.
    We normalize each directory's month to the first day and filter.
    """
    entries = _safe_mlsd(ftp, MONTHLY_DIR)
    months: list[tuple[date, str]] = []
    for name, facts in entries:
        if _MONTH_RE.match(name):
            y, m = map(int, name.split("-")[:2])
            month_key = date(y, m, 1)
            if month_key >= date(since.year, since.month, 1):
                months.append((month_key, name))
    months.sort()
    results: list[str] = []
    for _, dirname in months:
        # structure is .../Monthly/<dirname>/SDF/
        sdf_dir = f"{MONTHLY_DIR}/{dirname}/SDF"
        for fname, facts in _safe_mlsd(ftp, sdf_dir):
            if fname.endswith(".sdf.gz"):
                results.append(f"{sdf_dir}/{fname}")
    return results


def remote_md5_path(remote_gz_path: str) -> str:
    return f"{remote_gz_path}.md5"


def get_changed_sdf_files(
    ftp: ftplib.FTP, since: date | None
) -> list[tuple[str, str, str]]:
    """
    Return a list of (remote_gz, remote_md5, source) to download/process.
    If 'since' is None, return the full snapshot (source='full').
    Otherwise, return Monthly SDFs since that date (source='monthly').
    """
    if since is None:
        gz = list_full_sdf_archives(ftp)
        return [(p, remote_md5_path(p), "full") for p in gz]
    monthly = list_monthly_sdf_archives_since(ftp, since)
    return [(p, remote_md5_path(p), "monthly") for p in monthly]
