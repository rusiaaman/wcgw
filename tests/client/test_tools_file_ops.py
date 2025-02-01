import os
import unittest
from unittest.mock import MagicMock, mock_open, patch

from wcgw.client.tools import (
    BASH_STATE,
    expand_user,
    write_file,
)
from wcgw.types_ import WriteIfEmpty


class TestToolsFileOps(unittest.TestCase):
    def setUp(self):
        from wcgw.client.tools import BASH_STATE, INITIALIZED, TOOL_CALLS

        global INITIALIZED, TOOL_CALLS
        INITIALIZED = False
        TOOL_CALLS = []
        if hasattr(BASH_STATE, "reset"):
            try:
                BASH_STATE.reset_shell()
            except Exception:
                pass
        self.mock_tokenizer = MagicMock()
        self.mock_tokenizer.encode.return_value.ids = [1, 2, 3]
        self.mock_tokenizer.decode.return_value = "decoded text"

    def test_expand_user(self):
        # Test with no docker ID
        result = expand_user("~/test/path")
        self.assertTrue(os.path.expanduser("~") in result)

        # Test with non-home path
        result = expand_user("/absolute/path")
        self.assertEqual(result, "/absolute/path")

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.open", new_callable=mock_open)
    def test_write_file_validation(self, mock_file, mock_mkdir):
        # Test relative path
        test_file = WriteIfEmpty(
            file_path="relative/path.txt", file_content="test content"
        )
        result = write_file(test_file, error_on_exist=False, max_tokens=100)
        self.assertIn("Failure: file_path should be absolute path", result)

        # Test OSError handling
        test_file = WriteIfEmpty(
            file_path="/test/file.txt", file_content="test content"
        )
        with patch("pathlib.Path.open", side_effect=OSError("Permission denied")):
            with patch("pathlib.Path.mkdir"):
                with patch("os.path.exists", return_value=False):
                    with patch("os.path.isabs", return_value=True):
                        result = write_file(
                            test_file, error_on_exist=False, max_tokens=100
                        )
                        self.assertIn("Error: Permission denied", result)

        # Test overwriting whitelisted file
        test_file = WriteIfEmpty(
            file_path="/test/file.txt", file_content="test content"
        )
        BASH_STATE.add_to_whitelist_for_overwrite("/test/file.txt")

        with patch("os.path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value="old content"):
                result = write_file(test_file, error_on_exist=True, max_tokens=100)
                self.assertIn("Success", result)

        # Test overwriting non-whitelisted file
        test_file = WriteIfEmpty(
            file_path="/test/new_file.txt", file_content="test content"
        )
        with patch("os.path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value="existing content"):
                result = write_file(test_file, error_on_exist=True, max_tokens=100)
                self.assertIn("Error: can't write to existing file", result)


if __name__ == "__main__":
    unittest.main()
