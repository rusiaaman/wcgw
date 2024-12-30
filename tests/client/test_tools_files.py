import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import tempfile
from pathlib import Path
from wcgw.client.tools import (
    write_file,
    read_image_from_shell,
    get_context_for_errors,
    save_out_of_context,
    truncate_if_over,
    ImageData,
    BASH_STATE,
)
from wcgw.types_ import WriteIfEmpty

class TestToolsFiles(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        BASH_STATE._is_in_docker = ""  # Reset docker state
        BASH_STATE._whitelist_for_overwrite.clear()  # Clear whitelist
        self.temp_dir = tempfile.mkdtemp()  # Create a temporary directory

    def tearDown(self):
        # Clean up temporary directory recursively 
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            for root, dirs, files in os.walk(self.temp_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(self.temp_dir)


    def test_write_file_validation(self):
        """Test write_file input validation"""
        # Test relative path
        test_file = WriteIfEmpty(file_path="relative/path.txt", file_content="test")
        result = write_file(test_file, error_on_exist=True, max_tokens=100)
        self.assertIn("Failure: file_path should be absolute path", result)

        # Test with empty content
        test_file = WriteIfEmpty(file_path=os.path.join(self.temp_dir, "test.txt"), file_content="")
        with patch('os.path.isabs', return_value=True):
            with patch('os.path.exists', return_value=False):
                result = write_file(test_file, error_on_exist=True, max_tokens=100)
                self.assertIn("Success", result)

    def test_write_file_existing(self):
        """Test write_file behavior with existing files"""
        test_file = WriteIfEmpty(file_path=os.path.join(self.temp_dir, "file.txt"), file_content="new content")
        
        with patch('os.path.isabs', return_value=True):
            with patch('os.path.exists', return_value=True):
                with patch('pathlib.Path.read_text', return_value="existing content"):
                    # Test with error_on_exist=True
                    result = write_file(test_file, error_on_exist=True, max_tokens=100)
                    self.assertIn("Error: can't write to existing file", result)
                    self.assertIn("existing content", result)

                    # Test with whitelisted file
                    BASH_STATE.add_to_whitelist_for_overwrite(os.path.join(self.temp_dir, "file.txt"))
                    with patch('pathlib.Path.open', mock_open()):
                        result = write_file(test_file, error_on_exist=True, max_tokens=100)
                        self.assertIn("Success", result)

    @patch('wcgw.client.tools.check_syntax')
    def test_write_file_syntax_check(self, mock_check):
        """Test write_file syntax checking"""
        # Setup syntax error mock
        mock_error = MagicMock()
        mock_error.description = "Invalid syntax"
        mock_error.errors = [(1, 0)]
        mock_check.return_value = mock_error

        test_file = WriteIfEmpty(file_path=os.path.join(self.temp_dir, "file.py"), file_content="invalid python")
        
        with patch('os.path.isabs', return_value=True):
            with patch('os.path.exists', return_value=False):
                with patch('pathlib.Path.open', mock_open()):
                    result = write_file(test_file, error_on_exist=True, max_tokens=100)
                    self.assertIn("Success", result)
                    self.assertIn("syntax errors", result)
                    self.assertIn("Invalid syntax", result)

    @patch('os.path.exists')
    @patch('os.path.isabs')
    @patch('builtins.open', new_callable=mock_open)
    def test_read_image_from_shell(self, mock_file, mock_isabs, mock_exists):
        """Test read_image_from_shell functionality"""
        # Setup mocks
        mock_isabs.return_value = True
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = b"test_image_data"
        
        # Test regular file read
        result = read_image_from_shell("/test/image.png")
        self.assertIsInstance(result, ImageData)
        self.assertEqual(result.media_type, "image/png")
        
        # Test non-existent file
        mock_exists.return_value = False
        with self.assertRaises(ValueError):
            read_image_from_shell("/nonexistent/image.png")

    @patch('wcgw.client.tools.default_enc')
    def test_get_context_for_errors(self, mock_enc):
        """Test get_context_for_errors functionality"""
        mock_enc.encode.return_value = [1, 2, 3]  # simulate tokens
        
        # Test with single error
        file_content = "line1\nline2\nline3\nline4\nline5"
        errors = [(2, 0)]  # Error on line 2
        result = get_context_for_errors(errors, file_content, max_tokens=100)
        self.assertIn("line2", result)
        self.assertIn("```", result)

        # Test with multiple errors
        errors = [(2, 0), (4, 0)]
        result = get_context_for_errors(errors, file_content, max_tokens=100)
        