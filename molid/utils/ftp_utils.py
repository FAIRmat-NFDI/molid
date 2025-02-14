import ftplib
import gzip
import time
from pathlib import Path

# Configuration
FTP_SERVER = "ftp.ncbi.nlm.nih.gov"
FTP_DIRECTORY = "/pubchem/Compound/CURRENT-Full/SDF/"

def validate_partial_file(file_path):
    """Validate the integrity of a partial .gz file."""
    try:
        with gzip.open(file_path, "rb") as gz_file:
            while gz_file.read(1024):  # Read small chunks to ensure decompressibility
                pass
        print(f"[INFO] Partial file {file_path.name} is valid.")
        return True
    except Exception as e:
        print(f"[ERROR] Partial file {file_path.name} is invalid: {e}")
        return False

def get_total_files_from_ftp():
    """Fetch the list of available files on the FTP server."""
    try:
        with ftplib.FTP(FTP_SERVER) as ftp:
            ftp.login(user="anonymous", passwd="guest@example.com")
            ftp.cwd(FTP_DIRECTORY)
            files = []
            ftp.retrlines("LIST", lambda x: files.append(x.split()[-1]))
            sdf_files = [f for f in files if f.endswith(".sdf.gz")]
            print(f"[INFO] Total .sdf.gz files available on server: {len(sdf_files)}")
            return sdf_files
    except Exception as e:
        raise RuntimeError(f"Failed to fetch file list from FTP server: {e}")

def validate_start_position(local_file_path, ftp_size):
    """Validate the start position for resuming a download."""
    start_position = 0
    if local_file_path.exists():
        if not validate_partial_file(local_file_path):
            print(f"[WARN] Invalid partial file {local_file_path.name}. Restarting download.")
            local_file_path.unlink()  # Delete the invalid file
            return 0
        start_position = local_file_path.stat().st_size
        print(f"[DEBUG] Resuming download for {local_file_path.name} from byte {start_position}.")

    # Ensure the start position is not greater than the FTP file size
    if start_position > ftp_size:
        print(f"[ERROR] Start position {start_position} exceeds file size {ftp_size}. Restarting download.")
        local_file_path.unlink()
        return 0

    return start_position

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
                print(f"[WARN] Server does not support REST. Restarting download for {file_name}.")
                local_file.truncate(0)  # Reset file and restart
                ftp.retrbinary(f"RETR {file_name}", local_file.write)
            else:
                raise  # Re-raise other errors

    # Validate the file size
    if local_file_path.stat().st_size == ftp_size:
        print(f"[INFO] Successfully downloaded: {file_name}")
        return True
    else:
        print(f"[ERROR] File size mismatch for {file_name}. Retrying...")
        return False

def download_file_with_resume(file_name, download_folder, max_retries=5):
    """Download a file from the FTP server with resume functionality and fallback for unsupported REST."""
    local_file_path = Path(download_folder) / file_name
    backoff = 5  # Initial backoff in seconds

    for attempt in range(1, max_retries + 1):
        try:
            with ftplib.FTP(FTP_SERVER, timeout=600) as ftp:
                ftp.set_pasv(True)
                ftp.login(user="anonymous", passwd="guest@example.com")
                ftp.cwd(FTP_DIRECTORY)

                # Get file size from the server
                ftp_size = ftp.size(file_name)
                print(f"[DEBUG] Server-reported file size for {file_name}: {ftp_size}")

                # Validate or calculate the start position
                start_position = validate_start_position(local_file_path, ftp_size)

                # Attempt to download the file
                if attempt_download(file_name, local_file_path, start_position, ftp):
                    return local_file_path

        except Exception as e:
            print(f"[ERROR] Attempt {attempt}/{max_retries} failed for {file_name}: {e}")

            # Clean up incomplete file before retrying
            if local_file_path.exists():
                print(f"[WARN] Deleting incomplete file: {local_file_path}")
                local_file_path.unlink()

            time.sleep(backoff)  # Wait before retrying
            backoff *= 2  # Exponential backoff

    print(f"[ERROR] Failed to download {file_name} after {max_retries} attempts.")
    if local_file_path.exists():
        local_file_path.unlink()  # Ensure no corrupt file is left behind
    return None
