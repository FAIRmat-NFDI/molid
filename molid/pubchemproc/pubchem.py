from __future__ import annotations

import logging
from pathlib import Path

from collections.abc import Callable
from typing import Any

from molid.pubchemproc.file_handler import (
    validate_gz_file,
    unpack_gz_file,
    cleanup_files,
    GzipValidationError,
    FileUnpackError,
)

logger = logging.getLogger(__name__)


# Fields used for processing SDF files (only a limited set)
FIELDS_TO_EXTRACT: dict[str, str] = {
    "CID": "PUBCHEM_COMPOUND_CID",
    "SMILES": "PUBCHEM_SMILES",
    "InChIKey": "PUBCHEM_IUPAC_INCHIKEY",
    "InChI": "PUBCHEM_IUPAC_INCHI",
    "Formula": "PUBCHEM_MOLECULAR_FORMULA",
}

def process_file(
    file_path: Path,
    fields_to_extract: dict[str, str]
) -> list[dict[str, str]]:
    """Extract specified fields from an .sdf file, returning a list of dicts."""
    data = []
    with open(file_path, "r") as file:
        compound_data = {}
        for line in file:
            line = line.strip()
            if line.startswith("> <"):
                property_name = line[3:-1]
                if property_name in fields_to_extract.values():
                    value = file.readline().strip()
                    key = [k for k, v in fields_to_extract.items() if v == property_name][0]
                    compound_data[key] = value
            elif line == "$$$$":
                if compound_data:
                    data.append(compound_data)
                compound_data = {}
    return data

def download_and_process_file(
    file_name: str,
    download_folder: Path | str,
    processed_folder: Path | str,
    fields_to_extract: dict[str, str],
    process_callback: Callable[[list[dict[str, Any]]], None]
) -> bool:
    """
    Download, unpack, process, and save a single file with tracking.
    """
    try:
        gz_path = Path(download_folder) / file_name
        validate_gz_file(gz_path)

        sdf_file_path = unpack_gz_file(gz_path, processed_folder)

        extracted_data = process_file(sdf_file_path, fields_to_extract)
        process_callback(extracted_data)

        cleanup_files(gz_path, sdf_file_path)
        logger.info("Successfully processed: %s", file_name)
        return True
    except (GzipValidationError, FileUnpackError) as e:
        logger.error("Processing failed for %s: %s", file_name, e)
        return False
    except Exception as e:
        logger.exception("Unexpected error while processing %s: %s", file_name, e)
        return False
