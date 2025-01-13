import json
import os
import unittest
from unittest.mock import mock_open, patch

from wcgw.client.memory import format_memory, get_app_dir_xdg, load_memory, save_memory
from wcgw.types_ import ContextSave


class TestMemory(unittest.TestCase):
    class MockTokens:
        def __init__(self, ids):
            self.ids = ids

        def __len__(self):
            return len(self.ids)

        def __getitem__(self, key):
            if isinstance(key, slice):
                return TestMemory.MockTokens(self.ids[key])
            return self.ids[key]

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
        """Test loading of memory data including bash state"""
        task_id = "test-id"
        memory_data = "# PROJECT ROOT = /project\nTest description\n*.py\nfile1.py"
        bash_state_data = {
            "bash_command_mode": {
                "bash_mode": "normal_mode",
                "allowed_commands": "all",
            },
            "file_edit_mode": {"allowed_globs": "all"},
            "write_if_empty_mode": {"allowed_globs": "all"},
            "whitelist_for_overwrite": [],
            "mode": "wcgw",
        }
        mock_encoder = lambda x: self.MockTokens([1, 2, 3])  # Simulate tokenizer output
        mock_decoder = lambda x: "Decoded text"  # Return fixed text for any input IDs

        # Mock both the memory file and bash state file
        from wcgw.client.memory import get_app_dir_xdg

        app_dir = get_app_dir_xdg()
        memory_dir = os.path.join(app_dir, "memory")
        mock_files = {
            os.path.join(memory_dir, f"{task_id}.txt"): memory_data,
            os.path.join(memory_dir, f"{task_id}_bash_state.json"): json.dumps(
                bash_state_data
            ),
        }

        def mock_open_file(filename, *args, **kwargs):
            content = mock_files.get(filename)
            if content is None:
                raise FileNotFoundError(filename)
            return mock_open(read_data=content)()

        with patch("builtins.open", side_effect=mock_open_file), \
             patch("os.path.exists", lambda x: x.endswith("_bash_state.json")):
            project_root, data, bash_state = load_memory(
                task_id, max_tokens=2, encoder=mock_encoder, decoder=mock_decoder
            )
            self.assertEqual(project_root, "")
            self.assertEqual(data, "Decoded text\n(... truncated)")
            self.assertEqual(
                bash_state, bash_state_data
            )  # Verify bash state was loaded

    def test_load_memory_with_tokens(self):
        """Test loading of memory data with token limit"""
        task_id = "test-id"
        memory_data = "# PROJECT ROOT = '/project'\nTest description\n*.py\nfile1.py"
        bash_state_data = {
            "bash_command_mode": {
                "bash_mode": "normal_mode",
                "allowed_commands": "all",
            },
            "file_edit_mode": {"allowed_globs": "all"},
            "write_if_empty_mode": {"allowed_globs": "all"},
            "whitelist_for_overwrite": [],
            "mode": "wcgw",
        }

        mock_encoder = lambda x: self.MockTokens([1, 2, 3])  # Simulate tokenizer output
        mock_decoder = lambda x: "truncated text"  # Return fixed text for any input IDs

        from wcgw.client.memory import get_app_dir_xdg

        app_dir = get_app_dir_xdg()
        memory_dir = os.path.join(app_dir, "memory")
        mock_files = {
            os.path.join(memory_dir, f"{task_id}.txt"): memory_data,
            os.path.join(memory_dir, f"{task_id}_bash_state.json"): json.dumps(
                bash_state_data
            ),
        }

        def mock_open_file(filename, *args, **kwargs):
            content = mock_files.get(filename)
            if content is None:
                raise FileNotFoundError(filename)
            return mock_open(read_data=content)()

        with patch("builtins.open", side_effect=mock_open_file), \
             patch("os.path.exists", lambda x: x.endswith("_bash_state.json")):
            project_root, data, bash_state = load_memory(
                task_id, max_tokens=2, encoder=mock_encoder, decoder=mock_decoder
            )

            # Since encoder returns [1, 2, 3] and decoder returns input unchanged,
            # only the first chunk (after truncation) should be returned plus the truncation message
            self.assertEqual(project_root, "")
            # Our test decoder returns unchanged input, so we get first token plus truncation message
            self.assertEqual(
                data, "truncated text\n(... truncated)"
            )  # Use the actual mock_decoder output
            self.assertEqual(
                bash_state, bash_state_data
            )  # Verify bash state was loaded


if __name__ == "__main__":
    unittest.main()
