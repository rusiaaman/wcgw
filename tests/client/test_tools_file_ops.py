import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import websockets
from websockets.exceptions import ConnectionClosedError
from websockets import frames
from pathlib import Path
from wcgw.client.tools import (
    BASH_STATE,
    read_image_from_shell,
    write_file,
    expand_user,
    serve_image_in_bg,
    ImageData,
)
from wcgw.types_ import WriteIfEmpty

class TestToolsFileOps(unittest.TestCase):
    def setUp(self):
        self.mock_tokenizer = MagicMock()
        self.mock_tokenizer.encode.return_value.ids = [1, 2, 3]
        self.mock_tokenizer.decode.return_value = "decoded text"

    @patch('os.path.exists')
    def test_read_image_with_docker(self, mock_exists):
        # Set up docker environment
        BASH_STATE.set_in_docker("test_container")
        
        mock_exists.return_value = True
        with patch('builtins.open', mock_open(read_data=b'test_image_data')):
            with patch('os.system', return_value=0):
                result = read_image_from_shell("/test/image.png")
                self.assertIsInstance(result, ImageData)
                self.assertEqual(result.media_type, "image/png")

        # Test docker copy failure
        with patch('os.system', return_value=1):
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

    @patch('wcgw.client.tools.syncconnect')
    def test_serve_image_in_bg(self, mock_connect):
        # Test successful image serving
        mock_websocket1 = MagicMock()
        mock_websocket1.send = MagicMock()
        mock_websocket2 = MagicMock()
        mock_websocket2.send = MagicMock()

        # First successful case
        mock_connect.side_effect = [
            type('Context', (), {
                '__enter__': lambda x: mock_websocket1,
                '__exit__': lambda x, exc_type, exc_val, exc_tb: None
            })()
        ]

        with patch('builtins.open', mock_open(read_data=b'test_image_data')):
            serve_image_in_bg("/test/image.jpg", "test-uuid", "test-name")
            mock_websocket1.send.assert_called_once()

        # Test retry case - first connection fails, second succeeds
        mock_websocket3 = MagicMock()
        rcvd_frame = frames.Close(code=1006, reason="Connection closed abnormally")
        sent_frame = frames.Close(code=1000, reason="Normal close")
        mock_websocket3.send.side_effect = ConnectionClosedError(rcvd_frame, sent_frame, True)
        mock_websocket4 = MagicMock()
        mock_websocket4.send = MagicMock()
        
        mock_connect.side_effect = [
            type('Context', (), {
                '__enter__': lambda x: mock_websocket3,
                '__exit__': lambda x, exc_type, exc_val, exc_tb: None
            })(),
            type('Context', (), {
                '__enter__': lambda x: mock_websocket4,
                '__exit__': lambda x, exc_type, exc_val, exc_tb: None
            })()
        ]

        with patch('builtins.open', mock_open(read_data=b'test_image_data')):
            serve_image_in_bg("/test/image.jpg", "test-uuid", "test-name")
            self.assertEqual(mock_websocket4.send.call_count, 1)

    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.open', new_callable=mock_open)
    def test_write_file_with_overwrite(self, mock_file, mock_mkdir):
        # Test overwriting whitelisted file
        test_file = WriteIfEmpty(file_path="/test/file.txt", file_content="test content")
        BASH_STATE.add_to_whitelist_for_overwrite("/test/file.txt")
        
        with patch('os.path.exists', return_value=True):
            with patch('pathlib.Path.read_text', return_value="old content"):
                result = write_file(test_file, error_on_exist=True, max_tokens=100)
                self.assertIn("Success", result)

        # Test overwriting non-whitelisted file
        test_file = WriteIfEmpty(file_path="/test/new_file.txt", file_content="test content")
        with patch('os.path.exists', return_value=True):
            with patch('pathlib.Path.read_text', return_value="existing content"):
                result = write_file(test_file, error_on_exist=True, max_tokens=100)
                self.assertIn("Error: can't write to existing file", result)

    @patch('os.system')
    def test_write_file_docker(self, mock_system):
        # Set up docker environment
        BASH_STATE.set_in_docker("test_container")

        test_file = WriteIfEmpty(file_path="/test/file.txt", file_content="test content")

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
        test_file = WriteIfEmpty(file_path="relative/path.txt", file_content="test content")
        result = write_file(test_file, error_on_exist=False, max_tokens=100)
        self.assertIn("Failure: file_path should be absolute path", result)

        # Test OSError handling
        test_file = WriteIfEmpty(file_path="/test/file.txt", file_content="test content")
        with patch('pathlib.Path.open', side_effect=OSError("Permission denied")):
            with patch('pathlib.Path.mkdir'):
                with patch('os.path.exists', return_value=False):
                    with patch('os.path.isabs', return_value=True):
                        result = write_file(test_file, error_on_exist=False, max_tokens=100)
                        self.assertIn("Error: Permission denied", result)

if __name__ == '__main__':
    unittest.main()
