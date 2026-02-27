from __future__ import annotations

import gzip
import hashlib
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class GzipValidationError(Exception):
    pass


class FileUnpackError(Exception):
    pass


def validate_gz_file(gz_file_path: Path) -> None:
    """Validate the integrity of a .gz file, or raise an error."""
    try:
        with gzip.open(gz_file_path, "rb") as gz_file:
            while gz_file.read(1024):
                pass
        logger.info("Validated: %s", gz_file_path.name)
    except Exception as e:
        logger.error("Invalid .gz file: %s - %s", gz_file_path.name, e)
        raise GzipValidationError(f"Invalid gzip file: {gz_file_path}") from e


def unpack_gz_file(gz_file_path: Path, output_folder: Path | str) -> Path:
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


def cleanup_files(*paths: Path | str) -> None:
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


def move_file(source: Path | str, destination: Path | str) -> None:
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


def read_expected_md5(md5_file_path: Path) -> str:
    """
    Read the first token of the .md5 file (the expected hash).
    """
    text = md5_file_path.read_text().strip()
    # format: "<md5sum>  filename"
    return text.split()[0]


def compute_md5(file_path: Path) -> str:
    """
    Compute the MD5 hash of the given file, in chunks.
    """
    h = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_md5(gz_file_path: Path, md5_file_path: Path) -> bool:
    """
    Return True if the computed MD5 of gz_file_path matches the one in md5_file_path.
    """
    expected = read_expected_md5(md5_file_path)
    actual = compute_md5(gz_file_path)
    if expected != actual:
        logger.error(
            "MD5 mismatch: %s (got %s, expected %s)",
            gz_file_path.name,
            actual,
            expected,
        )
    return expected == actual
