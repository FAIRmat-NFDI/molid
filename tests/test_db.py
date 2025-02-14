import unittest
import os
import io
from unittest.mock import patch
from molid.db.db_manager import create_database, update_database, main

class TestDBManager(unittest.TestCase):
    def setUp(self):
        """Set up a temporary database file for testing."""
        self.test_db_file = "test_db_manager.db"
        self.mock_sdf_files = ["file1.sdf.gz", "file2.sdf.gz"]

    def tearDown(self):
        """Clean up the test database file."""
        if os.path.exists(self.test_db_file):
            os.remove(self.test_db_file)

    @patch("molid.db.db_manager.initialize_database")
    def test_create_database(self, mock_initialize_database):
        """Test creating a new database."""
        create_database(self.test_db_file)
        mock_initialize_database.assert_called_once_with(
            self.test_db_file,
            {
                "SMILES": "PUBCHEM_SMILES",
                "InChIKey": "PUBCHEM_IUPAC_INCHIKEY",
                "InChI": "PUBCHEM_IUPAC_INCHI",
                "Formula": "PUBCHEM_MOLECULAR_FORMULA"
            }
        )

    @patch("molid.db.db_manager.get_total_files_from_ftp")
    @patch("molid.db.db_manager.download_file_with_resume")
    @patch("molid.db.db_manager.download_and_process_file")
    @patch("molid.db.db_manager.check_disk_space")
    def test_update_database(self, mock_check_disk_space, mock_download_and_process_file,
    mock_download_file_with_resume, mock_get_total_files):
        """Test updating an existing database."""
        mock_check_disk_space.return_value = None  # Bypass disk space check
        mock_get_total_files.return_value = self.mock_sdf_files
        mock_download_file_with_resume.return_value = "local_file_path"

        # Create a dummy database file
        open(self.test_db_file, "w").close()

        update_database(self.test_db_file, max_files=2)

        mock_get_total_files.assert_called_once()
        self.assertEqual(mock_download_file_with_resume.call_count, 2)
        self.assertEqual(mock_download_and_process_file.call_count, 2)

    @patch("builtins.print")
    def test_use_existing_database(self, mock_print):
        """Test using an existing database without modification."""
        # Create a dummy file
        open(self.test_db_file, "w").close()

        with patch("sys.argv", ["molid-db-manager", "use", "--db-file", self.test_db_file]):
            main()

        mock_print.assert_any_call(f"[INFO] Using existing database: {self.test_db_file}")

    @patch("builtins.print")
    def test_use_nonexistent_database(self, mock_print):
        """Test error when using a non-existent database."""
        with patch("sys.argv", ["molid-db-manager", "use", "--db-file", "nonexistent.db"]):
            with self.assertRaises(SystemExit):  # Expect SystemExit
                main()

        mock_print.assert_any_call("[ERROR] The specified database file 'nonexistent.db' does not exist. Please provide a valid database.")

    @patch("sys.stdout", new_callable=io.StringIO)  # Capture stdout instead of mocking print
    def test_invalid_command(self, mock_stdout):
        """Test behavior when an invalid command is provided."""
        with patch("sys.argv", ["molid-db-manager"]):
            with self.assertRaises(SystemExit):  # Ensure argparse exits when no command is provided
                main()

        # Get the captured output
        captured_output = mock_stdout.getvalue()

        # Check if the help message was printed
        assert "usage: molid-db-manager [-h] {create,update,use} ..." in captured_output


