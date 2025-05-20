import logging
from pathlib import Path
from molid.pubchemproc.file_handler import (
    validate_gz_file,
    unpack_gz_file,
    cleanup_files,
    GzipValidationError,
    FileUnpackError,
)

logger = logging.getLogger(__name__)


# Fields used for processing SDF files (only a limited set)
FIELDS_TO_EXTRACT = {
    "SMILES": "PUBCHEM_SMILES",
    "InChIKey": "PUBCHEM_IUPAC_INCHIKEY",
    "InChI": "PUBCHEM_IUPAC_INCHI",
    "Formula": "PUBCHEM_MOLECULAR_FORMULA",
}

def process_file(file_path, fields_to_extract):
    """Extract data from an .sdf file."""
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
                    if "InChIKey" in compound_data:
                        compound_data["InChIKey14"] = compound_data["InChIKey"][:14]
                    data.append(compound_data)
                compound_data = {}
    return data

def download_and_process_file(file_name, download_folder, processed_folder, fields_to_extract, process_callback):
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
