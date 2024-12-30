"""Tests for file operation functionality in tools.py"""
import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import tempfile
from tempfile import NamedTemporaryFile, TemporaryDirectory, gettempdir
from pathlib import Path
from wcgw.client.tools import (
    write_file,
    read_image_from_shell,
    get_context_for_errors,
    save_out_of_context,
    truncate_if_over,
    lines_replacer,
    find_least_edit_distance_substring,
    BASH_STATE,
)
from wcgw.types_ import WriteIfEmpty

class TestFileOperations(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        BASH_STATE.reset()

    def test_write_file_validation(self):
        """Test write_file input validation"""
        # Test relative path
        test_file = WriteIfEmpty(file_path="relative/path.txt", file_content="test")
        result = write_file(test_file, error_on_exist=True, max_tokens=100)
        self.assertIn("Failure: file_path should be absolute path", result)

        # Test with empty content
        with TemporaryDirectory() as tmpdir:
            test_file = WriteIfEmpty(
                file_path=os.path.join(tmpdir, "file.txt"),
                file_content=""
            )
        with patch('os.path.isabs', return_value=True):
            with patch('os.path.exists', return_value=False):
                result = write_file(test_file, error_on_exist=True, max_tokens=100)
                self.assertIn("Success", result)

    def test_write_file_existing(self):
        """Test write_file behavior with existing files"""
        with TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "file.txt")
            test_file = WriteIfEmpty(
                file_path=file_path,
                file_content="new content"
            )
            
            # Create the file with existing content
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                f.write("existing content")

            # Test with error_on_exist=True
            result = write_file(test_file, error_on_exist=True, max_tokens=100)
            self.assertIn("Error: can't write to existing file", result)
            self.assertIn("existing content", result)

            # Test with whitelisted file
            BASH_STATE.add_to_whitelist_for_overwrite(file_path)
            result = write_file(test_file, error_on_exist=True, max_tokens=100)
            self.assertIn("Success", result)

    def test_write_file_syntax_check(self):
        """Test write_file syntax checking"""
        # Create mock syntax checker
        mock_checker = MagicMock()
        mock_checker.description = "Invalid syntax"
        mock_checker.errors = [(1, 0)]  # Error at line 1, col 0
        
        # Setup test file
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value.ids = [1, 2, 3]  # Mock token encoding
        mock_encoder.decode.return_value = "mocked content"
        
        with TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.py")
            test_file = WriteIfEmpty(file_path=file_path, file_content="invalid code")
            
            # Setup patches
            with patch('wcgw.client.tools.check_syntax', return_value=mock_checker):
                with patch('wcgw.client.tools.default_enc', mock_encoder):
                    # Call function and check result
                    result = write_file(test_file, error_on_exist=True, max_tokens=100)
                    self.assertIn("Success", result)
                    self.assertIn("syntax errors", result)
                    self.assertIn("Invalid syntax", result)
                    self.assertIn("tree-sitter reported syntax errors", result)

    def test_read_image_from_shell(self):
        """Test read_image_from_shell functionality"""
        # Test regular file read
        with patch('os.path.exists', return_value=True):
            with patch('os.path.isabs', return_value=True):
                with patch('builtins.open', mock_open(read_data=b"test_image_data")):
                    result = read_image_from_shell("/test/image.png")
                    self.assertEqual(result.media_type, "image/png")
                    self.assertEqual(
                        result.data, 
                        "dGVzdF9pbWFnZV9kYXRh"  # base64 of "test_image_data"
                    )

        # Test non-existent file
        with patch('os.path.exists', return_value=False):
            with patch('os.path.isabs', return_value=True):
                with self.assertRaises(ValueError):
                    read_image_from_shell("/nonexistent/image.png")

    def test_get_context_for_errors(self):
        """Test get_context_for_errors functionality"""
        file_content = "line1\nline2\nline3\nline4\nline5"
        errors = [(2, 0)]  # Error on line 2
        
        # Test with sufficient token limit
        with patch('wcgw.client.tools.default_enc') as mock_enc:
            mock_enc.encode.return_value.ids = [1, 2, 3]  # Simulate few tokens
            result = get_context_for_errors(errors, file_content, max_tokens=100)
            self.assertIn("line2", result)
            self.assertIn("```", result)

        # Test with limited tokens
        with patch('wcgw.client.tools.default_enc') as mock_enc:
            # Return long token sequences to trigger token limit
            mock_enc.encode.return_value = MagicMock()
            mock_enc.encode.return_value.ids = list(range(200))  # Long token sequence
            mock_enc.encode.return_value.__len__ = lambda _: 200  # Make len() return 200
            
            # Use small token limit
            result = get_context_for_errors(errors, file_content, max_tokens=1)
            self.assertEqual(result, "Please re-read the file to understand the context")

    def test_save_out_of_context(self):
        """Test save_out_of_context functionality"""
        content = "Test content"
        suffix = ".txt"

        filepath = save_out_of_context(content, suffix)
        try:
            # Verify file exists and has correct content  
            self.assertTrue(os.path.exists(filepath))
            self.assertTrue(filepath.startswith(gettempdir()))
            self.assertTrue(filepath.endswith(suffix))
            with open(filepath, 'r') as f:
                self.assertEqual(f.read(), content)
        finally:
            # Cleanup
            if os.path.exists(filepath):
                os.remove(filepath)

    def test_find_least_edit_distance_substring(self):
        """Test find_least_edit_distance_substring functionality"""
        content = [
            "def test():",
            "    print('test')",
            "",
            "def another():",
            "    print('another')",
        ]
        
        # Test exact match
        search = [
            "def test():",
            "    print('test')",
        ]
        matched_lines, context = find_least_edit_distance_substring(content, search)
        self.assertEqual(matched_lines, search)
        
        # Test partial match
        search = [
            "def tst():",  # Typo
            "    print('test')",
        ]
        matched_lines, context = find_least_edit_distance_substring(content, search)
        self.assertTrue(any("test" in line for line in matched_lines))

    def test_lines_replacer(self):
        """Test lines_replacer functionality"""
        content_lines = [
            "def test():",
            "    print('old')",
            "    return True",
        ]
        
        # Test successful replacement
        search_lines = [
            "    print('old')",
        ]
        replace_lines = [
            "    print('new')",
        ]
        result = lines_replacer(content_lines, search_lines, replace_lines)
        self.assertIn("print('new')", result)
        self.assertIn("def test():", result)
        
        # Test empty input handling
        with self.assertRaises(ValueError):
            lines_replacer(content_lines, [], replace_lines)  # Empty search
        
        with self.assertRaises(ValueError):
            lines_replacer([], search_lines, replace_lines)  # Empty content
            
        # Test empty file with empty search (special case)
        result = lines_replacer([], [], ["new content"])
        self.assertEqual(result, "new content")