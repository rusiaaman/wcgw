import os
import unittest
from unittest.mock import MagicMock, mock_open, patch

from wcgw.client.tools import (
    BASH_STATE,
    ImageData,
    expand_user,
    read_image_from_shell,
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

    @patch("os.path.exists")
    def test_read_image_with_docker(self, mock_exists):
        # Set up docker environment
        BASH_STATE.set_in_docker("test_container")

        mock_exists.return_value = True
        with patch("builtins.open", mock_open(read_data=b"test_image_data")):
            with patch("os.system", return_value=0):
                result = read_image_from_shell("/test/image.png")
                self.assertIsInstance(result, ImageData)
                self.assertEqual(result.media_type, "image/png")

        # Test docker copy failure
        with patch("os.system", return_value=1):
            with self.assertRaises(Exception):
                read_image_from_shell("/test/image.png")

        # Reset docker state
        BASH_STATE._is_in_docker = ""

    def test_expand_user(self):
        # Test with no docker ID
        result = expand_user("~/test/path", None)
        self.assertTrue(os.path.expanduser("~") in result)

        # Test with docker ID
        result = expand_user("~/test/path", "test_container")
        self.assertEqual(result, "~/test/path")

        # Test with non-home path
        result = expand_user("/absolute/path", None)
        self.assertEqual(result, "/absolute/path")

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.open", new_callable=mock_open)
    def test_write_file_with_overwrite(self, mock_file, mock_mkdir):
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

    @patch("os.system")
    def test_write_file_docker(self, mock_system):
        # Set up docker environment
        BASH_STATE.set_in_docker("test_container")

        test_file = WriteIfEmpty(
            file_path="/test/file.txt", file_content="test content"
        )

        # Test successful write
        mock_system.return_value = 0
        result = write_file(test_file, error_on_exist=False, max_tokens=100)
        self.assertIn("Success", result)

        # Test directory creation failure
        mock_system.return_value = 1
        result = write_file(test_file, error_on_exist=False, max_tokens=100)
        self.assertIn("Error: Write failed with code", result)

        # Reset docker state
        BASH_STATE._is_in_docker = ""

    def test_write_file_validation(self):
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


if __name__ == "__main__":
    unittest.main()
