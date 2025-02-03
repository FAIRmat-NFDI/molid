import unittest
import gzip
import os
import sqlite3
from pathlib import Path
from molid.pubchemproc.pubchem import process_file
from molid.pubchemproc.file_handler import validate_gz_file, unpack_gz_file, cleanup_files
from molid.pubchemproc.query import query_pubchem_database

class TestPubChemProcessing(unittest.TestCase):
    def setUp(self):
        """Set up temporary files and folders for testing."""
        self.sample_gz_path = Path("test_sample.sdf.gz")
        self.extracted_folder = Path("test_processed")
        self.sample_sdf_path = self.extracted_folder / "test_sample.sdf"
        self.sample_sdf_content = """\
        > <PUBCHEM_SMILES>
        CCO

        > <PUBCHEM_IUPAC_INCHIKEY>
        ZMXDDKWLCZADIW-UHFFFAOYSA-N

        $$$$
        """
        self.extracted_folder.mkdir(exist_ok=True)

        # Create a dummy .gz file for testing
        with gzip.open(self.sample_gz_path, "wb") as gz_file:
            gz_file.write(self.sample_sdf_content.encode())

    def tearDown(self):
        """Clean up temporary files and folders."""
        cleanup_files(self.sample_gz_path, self.extracted_folder)

    def test_validate_gz_file(self):
        """Test validating a .gz file."""
        result = validate_gz_file(self.sample_gz_path)
        self.assertTrue(result)

    def test_unpack_gz_file(self):
        """Test unpacking a .gz file."""
        unpacked_file = unpack_gz_file(self.sample_gz_path, self.extracted_folder)
        self.assertTrue(unpacked_file.exists())
        self.assertEqual(unpacked_file.read_text(), self.sample_sdf_content)

    def test_process_file(self):
        """Test extracting data from an .sdf file."""
        # Ensure the .gz file is unpacked first
        unpack_gz_file(self.sample_gz_path, self.extracted_folder)
        result = process_file(self.sample_sdf_path, {"SMILES": "PUBCHEM_SMILES", "InChIKey": "PUBCHEM_IUPAC_INCHIKEY"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["SMILES"], "CCO")
        self.assertEqual(result[0]["InChIKey"], "ZMXDDKWLCZADIW-UHFFFAOYSA-N")

class TestXYZQueryIntegration(unittest.TestCase):
    def setUp(self):
        """Set up a temporary database and sample XYZ file for testing."""
        self.database_file = "test_compounds.db"
        self.xyz_file = "test_water.xyz"

        # Create a temporary database
        self.connection = sqlite3.connect(self.database_file)
        cursor = self.connection.cursor()
        cursor.execute("""
            CREATE TABLE compound_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                InChIKey TEXT UNIQUE,
                SMILES TEXT,
                InChI TEXT,
                CAS TEXT
            )
        """)
        cursor.execute("INSERT INTO compound_data (InChIKey, SMILES, InChI, CAS) VALUES (?, ?, ?, ?)",
                       ("XLYOFNOQVPJJNP-UHFFFAOYSA-N", "O", "InChI=1S/H2O/h1H2", "7732-18-5"))
        self.connection.commit()

        # Create a temporary XYZ file (water molecule)
        with open(self.xyz_file, "w") as xyz:
            xyz.write("""3

            O       0.00000       0.00000       0.00000
            H       0.00000       0.75700       0.58600
            H       0.00000      -0.75700       0.58600
            """)

    def tearDown(self):
        """Clean up temporary files and database."""
        self.connection.close()
        os.remove(self.database_file)
        os.remove(self.xyz_file)

    def test_query_pubchem_database(self):
        """Test querying a PubChem database using an XYZ file."""
        inchikey, results = query_pubchem_database(self.xyz_file, self.database_file)

        # Assert InChIKey matches expected value
        self.assertEqual(inchikey, "XLYOFNOQVPJJNP-UHFFFAOYSA-N")

        # Assert query results contain expected values
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], "XLYOFNOQVPJJNP-UHFFFAOYSA-N")  # InChIKey
        self.assertEqual(results[0][2], "O")  # SMILES
        self.assertEqual(results[0][3], "InChI=1S/H2O/h1H2")  # InChI
        self.assertEqual(results[0][4], "7732-18-5")  # CAS Number
