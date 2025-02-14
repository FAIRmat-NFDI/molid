import unittest
import gzip
import os
from unittest.mock import MagicMock, patch
from pathlib import Path
from molid.utils.ftp_utils import (
    validate_partial_file,
    get_total_files_from_ftp,
    validate_start_position,
    attempt_download
)
from molid.pubchemproc.file_handler import validate_gz_file, unpack_gz_file, cleanup_files, move_file


class TestFileHandler(unittest.TestCase):
    def setUp(self):
        """Set up temporary files and folders for testing."""
        self.sample_gz_path = Path("test_sample.sdf.gz")
        self.sample_sdf_content = "Test content for unpacking."
        self.extracted_folder = Path("test_processed")
        self.destination_file = Path("test_moved.sdf")
        self.extracted_folder.mkdir(exist_ok=True)

        # Create a dummy .gz file for testing
        with gzip.open(self.sample_gz_path, "wb") as gz_file:
            gz_file.write(self.sample_sdf_content.encode())

    def tearDown(self):
        """Clean up temporary files and folders."""
        cleanup_files(self.sample_gz_path, self.extracted_folder, self.destination_file)

    def test_validate_gz_file(self):
        """Test validating a .gz file."""
        result = validate_gz_file(self.sample_gz_path)
        self.assertTrue(result)

    def test_unpack_gz_file(self):
        """Test unpacking a .gz file."""
        unpacked_file = unpack_gz_file(self.sample_gz_path, self.extracted_folder)
        self.assertTrue(unpacked_file.exists())
        self.assertEqual(unpacked_file.read_text(), self.sample_sdf_content)

    def test_cleanup_files(self):
        """Test cleaning up files."""
        file_to_delete = self.sample_gz_path
        cleanup_files(file_to_delete)
        self.assertFalse(file_to_delete.exists())

    def test_move_file(self):
        """Test moving a file."""
        unpacked_file = unpack_gz_file(self.sample_gz_path, self.extracted_folder)
        move_file(unpacked_file, self.destination_file)
        self.assertTrue(self.destination_file.exists())
        self.assertFalse(unpacked_file.exists())


class TestFTPUtils(unittest.TestCase):
    def setUp(self):
        """Set up temporary test files."""
        self.test_file = Path("test_partial_file.gz")
        with gzip.open(self.test_file, "wb") as f:
            f.write(b"Test content")
        self.mock_ftp = MagicMock()

    def tearDown(self):
        """Clean up temporary test files."""
        if self.test_file.exists():
            self.test_file.unlink()

    def test_validate_partial_file(self):
        """Test validation of partial files."""
        result = validate_partial_file(self.test_file)
        self.assertTrue(result)

    def test_validate_partial_file_invalid(self):
        """Test invalid partial file handling."""
        with open(self.test_file, "wb") as f:
            f.write(b"corrupted content")
        result = validate_partial_file(self.test_file)
        self.assertFalse(result)

    @patch('molid.utils.ftp_utils.ftplib.FTP')
    def test_get_total_files_from_ftp_success(self, mock_ftp_class):
        # Create a mock FTP instance for use within the context manager.
        mock_ftp_instance = MagicMock()
        mock_ftp_class.return_value.__enter__.return_value = mock_ftp_instance

        # Simulated FTP directory listing.
        fake_lines = [
            "-rw-r--r-- 1 owner group file1.sdf.gz",
            "-rw-r--r-- 1 owner group file2.txt",
            "-rw-r--r-- 1 owner group file3.sdf.gz",
        ]

        # Define a fake retrlines method to call the provided callback for each fake line.
        def fake_retrlines(command, callback):
            for line in fake_lines:
                callback(line)
        mock_ftp_instance.retrlines.side_effect = fake_retrlines

        # Patch the built-in print to capture output.
        with patch("builtins.print") as mock_print:
            result = get_total_files_from_ftp()

        # Only files ending with '.sdf.gz' should be returned.
        expected_files = ["file1.sdf.gz", "file3.sdf.gz"]
        self.assertEqual(result, expected_files)

        # Verify that the FTP login and directory change were called with the correct parameters.
        mock_ftp_instance.login.assert_called_once_with(user="anonymous", passwd="guest@example.com")
        mock_ftp_instance.cwd.assert_called_once_with("/pubchem/Compound/CURRENT-Full/SDF/")

        # Verify that the print statement includes the correct count.
        mock_print.assert_any_call(f"[INFO] Total .sdf.gz files available on server: {len(expected_files)}")

    @patch('molid.utils.ftp_utils.ftplib.FTP')
    def test_get_total_files_from_ftp_failure(self, mock_ftp_class):
        # Set up a mock FTP instance where login fails.
        mock_ftp_instance = MagicMock()
        mock_ftp_class.return_value.__enter__.return_value = mock_ftp_instance
        mock_ftp_instance.login.side_effect = Exception("Login failed")

        # Ensure that a RuntimeError is raised with the expected error message.
        with self.assertRaises(RuntimeError) as context:
            get_total_files_from_ftp()
        self.assertIn("Failed to fetch file list from FTP server: Login failed", str(context.exception))

    def test_validate_start_position(self):
        """Test validation of start position for resuming downloads."""
        local_file = self.test_file
        ftp_size = local_file.stat().st_size
        start_position = validate_start_position(local_file, ftp_size)
        self.assertEqual(start_position, ftp_size)

    def test_validate_start_position_invalid(self):
        """Test invalid start position handling."""
        local_file = self.test_file
        ftp_size = local_file.stat().st_size - 10
        start_position = validate_start_position(local_file, ftp_size)
        self.assertEqual(start_position, 0)

    def test_attempt_download_success(self):
        """Test successful file download."""
        self.mock_ftp.size.return_value = self.test_file.stat().st_size
        with patch("builtins.open", unittest.mock.mock_open()) as mock_file:
            result = attempt_download("file.sdf.gz", self.test_file, 0, self.mock_ftp)
            self.assertTrue(result)

    def test_attempt_download_file_size_mismatch(self):
        """Test file size mismatch during download."""
        self.mock_ftp.size.return_value = self.test_file.stat().st_size + 10
        with patch("builtins.open", unittest.mock.mock_open()) as mock_file:
            result = attempt_download("file.sdf.gz", self.test_file, 0, self.mock_ftp)
            self.assertFalse(result)
