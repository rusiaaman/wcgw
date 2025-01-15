"""Tests for user interaction functionality in tools.py"""

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from wcgw.client.tools import (
    BASH_STATE,
    get_status,
    save_out_of_context,
    truncate_if_over,
    update_repl_prompt,
)


class TestUserInteraction(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        BASH_STATE.reset_shell()

    def test_update_repl_prompt(self):
        """Test REPL prompt updating"""
        with patch("wcgw.client.tools.BASH_STATE") as mock_state:
            mock_state.shell = MagicMock()
            mock_state.shell.before = "new_prompt"
            mock_state.shell.expect.return_value = 1

            # Test valid prompt update
            result = update_repl_prompt("wcgw_update_prompt()")
            self.assertTrue(result)

            # Test invalid command
            result = update_repl_prompt("invalid_command")
            self.assertFalse(result)

    def test_get_status(self):
        """Test status reporting"""
        with patch("wcgw.client.tools.BASH_STATE") as mock_state:
            # Test pending state
            mock_state.state = "pending"
            mock_state.cwd = "/test/dir"
            mock_state.get_pending_for.return_value = "10 seconds"

            status = get_status()
            self.assertIn("status = still running", status)
            self.assertIn("running for = 10 seconds", status)
            self.assertIn("cwd = /test/dir", status)

            # Test completed state
            mock_state.state = "repl"
            mock_state.update_cwd.return_value = "/test/dir2"
            with patch("wcgw.client.tools._ensure_env_and_bg_jobs", return_value=2):
                status = get_status()
                self.assertIn(
                    "status = process exited; 2 background jobs running", status
                )
                self.assertIn("cwd = /test/dir2", status)

    def test_save_out_of_context(self):
        """Test saving content to temporary files"""
        content = "Test content"
        suffix = ".txt"

        # Test saving content
        filepath = save_out_of_context(content, suffix)
        self.assertTrue(os.path.exists(filepath))

        # Verify content was saved correctly
        saved_content = Path(filepath).read_text()
        self.assertEqual(saved_content, content)

        # Test saving with different suffixes
        filepath_py = save_out_of_context("def test(): pass", ".py")
        self.assertTrue(filepath_py.endswith(".py"))

        # Test saving empty content
        filepath_empty = save_out_of_context("", ".txt")
        self.assertTrue(os.path.exists(filepath_empty))
        self.assertEqual(Path(filepath_empty).read_text(), "")

        # Cleanup
        for path in [filepath, filepath_py, filepath_empty]:
            os.remove(path)

    def test_truncate_if_over(self):
        """Test content truncation based on token limits"""
        with patch("wcgw.client.tools.default_enc") as mock_enc:
            # Test content under limit
            content = "short content"
            mock_enc.encode.return_value = MagicMock(ids=list(range(5)))  # Under limit
            result = truncate_if_over(content, max_tokens=10)
            self.assertEqual(
                result, content
            )  # Should return original content when under limit
            self.assertEqual(
                mock_enc.decode.call_count, 0
            )  # Decode shouldn't be called

            # Test with content over limit
            long_content = "very long content" * 50
            mock_encoding = MagicMock()
            mock_encoding.ids = list(range(200))  # Over limit
            mock_encoding.__len__.return_value = 200  # Make len(tokens) return 200
            mock_enc.encode.return_value = mock_encoding
            mock_enc.decode.return_value = "truncated content"

            result = truncate_if_over(long_content, max_tokens=100)

            # In truncate_if_over: max(0, max_tokens - 100) = max(0, 100-100)
            truncated_ids = []  # Since 100-100 = 0, max(0, 0) = 0
            mock_enc.decode.assert_called_once_with(truncated_ids)
            self.assertEqual(result, "truncated content\n(...truncated)")
            self.assertIn("truncated content", result)

            # Test with no token limit
            result = truncate_if_over(long_content, max_tokens=None)
            self.assertEqual(result, long_content)

            # Test with zero token limit
            result = truncate_if_over(content, max_tokens=0)
            self.assertEqual(result, content)


if __name__ == "__main__":
    unittest.main()
