"""Tests for file operation functionality in tools.py"""

import os
import shutil
import tempfile
import unittest
from tempfile import gettempdir
from unittest.mock import MagicMock, mock_open, patch

from wcgw.client.tools import (
    BASH_STATE,
    get_context_for_errors,
    read_image_from_shell,
    save_out_of_context,
    truncate_if_over,
    write_file,
)
from wcgw.types_ import WriteIfEmpty


class TestFileOperations(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test case"""
        self.maxDiff = None
        self.test_dir = tempfile.mkdtemp()
        self.test_file_path = os.path.join(self.test_dir, "test_file.py")
        BASH_STATE.add_to_whitelist_for_overwrite(self.test_file_path)
        # Mock command_run for Docker tests
        self.mock_command_run_patcher = patch("wcgw.client.tools.command_run")
        self.mock_command_run = self.mock_command_run_patcher.start()
        self.mock_command_run.return_value = (0, "", "")

    def tearDown(self):
        """Clean up test environment after each test case"""
        self.mock_command_run_patcher.stop()
        shutil.rmtree(self.test_dir)
        BASH_STATE.set_in_docker("")

    def test_truncate_if_over(self):
        """Test content truncation based on token limit"""
        content = "test" * 100

        # Test with no limit
        result = truncate_if_over(content, None)
        self.assertEqual(result, content)

        # Test with limit
        with patch("wcgw.client.tools.default_enc") as mock_enc:
            # Create mock token list that exceeds max_tokens limit
            token_ids = list(range(1000))  # 1000 tokens to ensure truncation
            mock_token_list = MagicMock()
            mock_token_list.ids = token_ids
            mock_token_list.__len__ = MagicMock(return_value=len(token_ids))
            mock_enc.encode.return_value = mock_token_list

            # Set up the decode behavior to return "truncated beginning" when truncated
            def mock_decode(token_list):
                if len(token_list) < len(token_ids):
                    return "truncated beginning"
                return content

            mock_enc.decode.side_effect = mock_decode

            # Test truncation with max_tokens=150 to trigger truncation
            result = truncate_if_over(content, 150)

            # Should truncate tokens to max(0, 150-100) = 50 and append truncation marker
            expected = "truncated beginning\n(...truncated)"
            self.assertEqual(result, expected)

            # Verify encode was called with original content
            mock_enc.encode.assert_called_once_with(content)

            # Verify decode was called with truncated token list
            mock_enc.decode.assert_called_once_with(
                token_ids[:50]
            )  # max(0, 150-100) = 50

    def test_read_image_from_shell(self):
        """Test read_image_from_shell functionality"""
        # Test regular file read
        with patch("os.path.exists", return_value=True):
            with patch("os.path.isabs", return_value=True):
                with patch("builtins.open", mock_open(read_data=b"test_image_data")):
                    result = read_image_from_shell("/test/image.png")
                    self.assertEqual(result.media_type, "image/png")
                    self.assertEqual(
                        result.data, "dGVzdF9pbWFnZV9kYXRh"
                    )  # base64 of "test_image_data"

        # Test non-existent file
        with patch("os.path.exists", return_value=False):
            with patch("os.path.isabs", return_value=True):
                with self.assertRaises(ValueError):
                    read_image_from_shell("/nonexistent/image.png")

    def test_get_context_for_errors(self):
        """Test get_context_for_errors functionality"""
        file_content = "line1\nline2\nline3\nline4\nline5"
        errors = [(2, 0)]  # Error on line 2

        context = get_context_for_errors(errors, file_content, None)
        self.assertIn("line2", context)
        self.assertIn("```", context)

        # Test with small token limit
        short_context = get_context_for_errors(errors, file_content, 10)
        self.assertEqual(
            short_context, "Please re-read the file to understand the context"
        )

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
            with open(filepath, "r") as f:
                self.assertEqual(f.read(), content)
        finally:
            # Cleanup
            if os.path.exists(filepath):
                os.remove(filepath)

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

        with patch("wcgw.client.tools.check_syntax", return_value=mock_checker):
            with patch("wcgw.client.tools.default_enc", mock_encoder):
                write_arg = WriteIfEmpty(
                    file_path=self.test_file_path, file_content="invalid code"
                )
                with patch("pathlib.Path.exists", return_value=False):
                    result = write_file(write_arg, error_on_exist=True, max_tokens=100)
                    self.assertIn("Success", result)
                    self.assertIn("syntax errors", result)
                    self.assertIn("Invalid syntax", result)
                    self.assertIn("tree-sitter reported syntax errors", result)


if __name__ == "__main__":
    unittest.main()
