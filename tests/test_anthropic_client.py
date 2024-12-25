import unittest
from unittest.mock import patch, mock_open, MagicMock
import base64
from wcgw.client.anthropic_client import parse_user_message_special, text_from_editor
from wcgw.client.tools import ImageData
import tempfile
import os
import json
from pathlib import Path


class TestAnthropicClient(unittest.TestCase):
    def setUp(self):
        self.console_mock = MagicMock()
    
    def test_parse_user_message_special_text_only(self):
        msg = "Hello\nThis is a test"
        result = parse_user_message_special(msg)
        self.assertEqual(result["role"], "user")
        self.assertEqual(len(result["content"]), 1)
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertEqual(result["content"][0]["text"], "Hello\nThis is a test")

    @patch("builtins.open")
    @patch("mimetypes.guess_type")
    def test_parse_user_message_special_with_image(self, mock_guess_type, mock_open):
        # Mock image data
        image_data = b"fake_image_data"
        mock_open.return_value.__enter__.return_value.read.return_value = image_data
        mock_guess_type.return_value = ("image/png", None)
        
        msg = "%image test.png\nSome text after"
        result = parse_user_message_special(msg)
        
        # Verify structure
        self.assertEqual(result["role"], "user")
        self.assertEqual(len(result["content"]), 2)
        
        # Verify image block
        self.assertEqual(result["content"][0]["type"], "image")
        self.assertEqual(result["content"][0]["source"]["type"], "base64")
        self.assertEqual(result["content"][0]["source"]["media_type"], "image/png")
        expected_b64 = base64.b64encode(image_data).decode("utf-8")
        self.assertEqual(result["content"][0]["source"]["data"], expected_b64)
        
        # Verify text block
        self.assertEqual(result["content"][1]["type"], "text")
        self.assertEqual(result["content"][1]["text"], "Some text after")

    @patch("builtins.input")
    def test_text_from_editor_direct_input(self, mock_input):
        mock_input.return_value = "Test direct input"
        result = text_from_editor(self.console_mock)
        self.assertEqual(result, "Test direct input")
        
    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    @patch("builtins.input")
    def test_text_from_editor_with_editor(self, mock_input, mock_run, mock_tempfile):
        # Set up mocks
        mock_input.return_value = ""  # Empty input triggers editor
        mock_tempfile.return_value.__enter__.return_value.name = "test.tmp"
        
        # Mock the editor content
        editor_content = "Content from editor"
        with patch("builtins.open", mock_open(read_data=editor_content)):
            result = text_from_editor(self.console_mock)
            
        self.assertEqual(result, editor_content)
        mock_run.assert_called_once()
        
    @patch("os.environ")
    def test_text_from_editor_custom_editor(self, mock_environ):
        # Test with custom editor
        mock_environ.get.return_value = "nano"
        with patch("builtins.input", return_value=""):
            with patch("tempfile.NamedTemporaryFile") as mock_tmp:
                mock_tmp.return_value.__enter__.return_value.name = "test.tmp"
                with patch("subprocess.run") as mock_run:
                    with patch("builtins.open", mock_open(read_data="Written in nano")):
                        result = text_from_editor(self.console_mock)
                        
        self.assertEqual(result, "Written in nano")
        mock_run.assert_called_once_with(["nano", "test.tmp"], check=True)


if __name__ == "__main__":
    unittest.main()
