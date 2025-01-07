import os
import unittest
from unittest.mock import mock_open, patch

from wcgw.client.memory import format_memory, get_app_dir_xdg, load_memory, save_memory
from wcgw.types_ import ContextSave


class TestMemory(unittest.TestCase):
    def test_get_app_dir_xdg(self):
        with patch.dict("os.environ", {"XDG_DATA_HOME": "/custom/data"}):
            result = get_app_dir_xdg()
            self.assertEqual(result, os.path.join("/custom/data", "wcgw"))

        with patch.dict("os.environ", {}, clear=True):
            with patch("os.path.expanduser") as mock_expanduser:
                mock_expanduser.return_value = "/home/user"
                result = get_app_dir_xdg()
                self.assertEqual(result, "/home/user/wcgw")

    def test_format_memory(self):
        task_memory = ContextSave(
            id="test-id",
            project_root_path="/project",
            description="Test description",
            relevant_file_globs=["*.py"],
        )
        relevant_files = "file1.py\nfile2.py"
        result = format_memory(task_memory, relevant_files)
        self.assertIn("# PROJECT ROOT = /project", result)
        self.assertIn("Test description", result)
        self.assertIn("*.py", result)
        self.assertIn("file1.py", result)

    def test_save_memory(self):
        task_memory = ContextSave(
            id="test-id",
            project_root_path="/project",
            description="Test description",
            relevant_file_globs=["*.py"],
        )
        relevant_files = "file1.py\nfile2.py"

        with patch("os.makedirs"), patch("builtins.open", mock_open()) as mock_file:
            result = save_memory(task_memory, relevant_files)
            self.assertIn("test-id.txt", result)
            mock_file().write.assert_called_once()

    def test_load_memory(self):
        task_id = "test-id"
        memory_data = "# PROJECT ROOT = /project\nTest description\n*.py\nfile1.py"
        mock_encoder = lambda x: [1, 2, 3]  # Simulate token encoding
        mock_decoder = lambda x: "Decoded text"  # Simulate token decoding

        with patch("builtins.open", mock_open(read_data=memory_data)):
            project_root, data = load_memory(
                task_id, max_tokens=None, encoder=mock_encoder, decoder=mock_decoder
            )
            self.assertEqual(project_root, "/project")
            self.assertIn("Test description", data)

    def test_load_memory_with_tokens(self):
        task_id = "test-id"
        memory_data = "# PROJECT ROOT = '/project'\nTest description\n*.py\nfile1.py"
        mock_encoder = lambda x: [1, 2, 3]  # Simulate token encoding
        mock_decoder = lambda x: x  # Don't decode in test

        with patch("builtins.open", mock_open(read_data=memory_data)):
            project_root, data = load_memory(
                task_id, max_tokens=10, encoder=mock_encoder, decoder=mock_decoder
            )
            self.assertEqual(project_root, "/project")
            # Mock decoder returns input unchanged, so we expect full data
            self.assertEqual(data, memory_data)


if __name__ == "__main__":
    unittest.main()
