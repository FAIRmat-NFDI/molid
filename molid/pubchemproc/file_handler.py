import gzip
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class GzipValidationError(Exception):
    pass

class FileUnpackError(Exception):
    pass

def validate_gz_file(gz_file_path):
    """Validate the integrity of a .gz file, or raise an error."""
    try:
        with gzip.open(gz_file_path, "rb") as gz_file:
            while gz_file.read(1024):
                pass
        logger.info("Validated: %s", gz_file_path.name)
    except Exception as e:
        logger.error("Invalid .gz file: %s - %s", gz_file_path.name, e)
        raise GzipValidationError(f"Invalid gzip file: {gz_file_path}") from e

def unpack_gz_file(gz_file_path, output_folder):
    """Unpack a .gz file or raise on failure."""
    extracted_file_path = Path(output_folder) / gz_file_path.stem
    try:
        with gzip.open(gz_file_path, "rb") as gz_file:
            with open(extracted_file_path, "wb") as output_file:
                shutil.copyfileobj(gz_file, output_file)
        logger.info("Unpacked: %s", gz_file_path.name)
        return extracted_file_path
    except Exception as e:
        logger.error("Failed to unpack %s: %s", gz_file_path.name, e)
        raise FileUnpackError(f"Could not unpack {gz_file_path}") from e

def cleanup_files(*paths):
    """Delete specified files or directories."""
    for path in paths:
        path = Path(path)
        if path.exists():
            if path.is_file():
                path.unlink()
                logger.info("File deleted: %s", path)
            elif path.is_dir():
                shutil.rmtree(path)
                logger.info("Directory deleted: %s", path)

def move_file(source, destination):
    """Move a file to a new location."""
    source_path = Path(source)
    destination_path = Path(destination)
    try:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination_path))
        logger.info("Moved file from %s to %s", source_path, destination_path)
    except Exception as e:
        logger.error("Failed to move %s: %s", source_path, e)
        raise
