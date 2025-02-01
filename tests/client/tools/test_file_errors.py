"""Tests for file operation error handling"""
import unittest
from unittest.mock import patch, MagicMock
from wcgw.client.tools import save_out_of_context

class TestFileErrors(unittest.TestCase):
    def test_save_out_of_context(self):
        """Test saving content out of context"""
        with patch('tempfile.NamedTemporaryFile', create=True) as mock_temp_file:
            mock_temp_file.return_value.__enter__.return_value.name = '/tmp/test.txt'
            with patch('builtins.open', create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file
                
                result = save_out_of_context("test content", ".txt")
                # Since we can't predict exact temp file name, just verify path and suffix
                self.assertTrue(result.startswith('/tmp/tmp'))
                self.assertTrue(result.endswith('.txt'))
                mock_file.write.assert_called_once_with("test content")