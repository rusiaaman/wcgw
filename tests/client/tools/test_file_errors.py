"""Tests for file operation error handling"""
import unittest
from unittest.mock import patch, MagicMock
from wcgw.client.tools import save_out_of_context, read_image_from_shell

class TestFileErrors(unittest.TestCase):
    def test_read_nonexistent_image(self):
        """Test reading a non-existent image file"""
        with patch('os.path.exists', return_value=False):
            with patch('os.path.isabs', return_value=True):
                with self.assertRaises(ValueError) as cm:
                    read_image_from_shell("/nonexistent/image.png")
                self.assertIn("does not exist", str(cm.exception))
                
    def test_read_image_docker_error(self):
        """Test handling of docker copy errors"""
        with patch('wcgw.client.tools.BASH_STATE') as mock_state:
            mock_state.is_in_docker = "test_container"
            with patch('os.system', return_value=1):  # Simulate docker cp failure
                with self.assertRaises(Exception) as cm:
                    read_image_from_shell("/test/image.png")
                self.assertIn("Error: Read failed", str(cm.exception))