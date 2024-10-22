import unittest
from unittest.mock import patch, mock_open
from src.wcgw.basic import text_from_editor, save_history, parse_user_message_special, Config
import os
import tempfile
import json
from pathlib import Path

class TestBasic(unittest.TestCase):
    @patch('builtins.input', return_value='Test message')
    def test_text_from_editor_direct_input(self, mock_input):
        # Mock console
        mock_console = patch('rich.console.Console').start()
        result = text_from_editor(mock_console)
        self.assertEqual(result, 'Test message')

    @patch('tempfile.NamedTemporaryFile')
    @patch('subprocess.run')
    @patch('builtins.input', return_value='')
    def test_text_from_editor_editor_input(self, mock_input, mock_run, mock_tempfile):
        # Setup tempfile mock
        mock_tempfile.return_value.__enter__.return_value.name = 'testfile.tmp'
        with patch('builtins.open', mock_open(read_data='Editor content')) as mock_file:
            mock_console = patch('rich.console.Console').start()
            result = text_from_editor(mock_console)
            mock_run.assert_called_once()  # Ensure the editor was called
            mock_file.assert_called_with('testfile.tmp', 'r')
            self.assertEqual(result, 'Editor content')

    def test_save_history(self):
        history = [{'role': 'user', 'content': 'Message 1'}, {'role': 'assistant', 'content': 'Response'}]
        session_id = 'abc123'
        expected_filename = '.wcgw/response_abc123.json'
        with patch('builtins.open', mock_open()) as mock_file:
            save_history(history, session_id)
            mock_file.assert_called_with(Path(expected_filename), 'w')
            # Capture all write calls
            write_calls = [call[0][0] for call in mock_file().write.call_args_list]
            # Recreate the expected write content
            expected_content = json.dumps(history, indent=3)
            # Ensure joined write calls match the expected content
            self.assertEqual(''.join(write_calls), expected_content)

    def test_parse_user_message_special(self):
        # Test parsing user message without special commands
        message = 'Hello world'
        result = parse_user_message_special(message)
        self.assertEqual(result['content'][0]['text'], 'Hello world')

        # Test parsing with special image command
        with patch('builtins.open', mock_open(read_data=b'image data')):
            with patch('mimetypes.guess_type', return_value=('image/png', None)):
                message = '%image test.png'
                result = parse_user_message_special(message)
                self.assertEqual(result['content'][0]['type'], 'image_url')
                self.assertTrue('data:image/png;base64,' in result['content'][0]['image_url']['url'])

if __name__ == '__main__':
    unittest.main()
