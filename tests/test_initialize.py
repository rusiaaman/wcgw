"""Tests for initialize functionality in tools.py"""

import os
import shutil
import unittest
from unittest.mock import MagicMock, patch

from wcgw.client.tools import BASH_STATE, initialize
from wcgw.types_ import CodeWriterMode, Modes


class TestInitialize(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        # Create a temporary test workspace path
        self.repo_context = "test_repo_context"
        self.test_workspace = os.path.join(os.getcwd(), "test_workspace")
        # Create test workspace dir
        os.makedirs(self.test_workspace, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_workspace):
            shutil.rmtree(self.test_workspace)
        BASH_STATE.reset_shell()

    def test_load_memory_error(self):
        """Test initialize handling when loading task memory fails"""
        # Mock load_memory to raise exception
        with patch("wcgw.client.tools.load_memory") as mock_load:
            mock_load.side_effect = Exception("Memory load failed")

            # Call initialize with a task_id
            result = initialize(
                any_workspace_path="",
                read_files_=[],
                task_id_to_resume="test_task_id",
                max_tokens=None,
                mode=Modes.wcgw,
            )

            # Verify error message is included in output
            self.assertIn('Error: Unable to load task with ID "test_task_id"', result)

            # Verify load_memory was called with correct parameters
            mock_load.assert_called_once_with(
                "test_task_id",
                None,  # max_tokens
                unittest.mock.ANY,  # encode lambda
                unittest.mock.ANY,  # decode lambda
            )

    def test_workspace_path_exists(self):
        """Test initialize handling when workspace path exists"""

        with (
            patch("os.path.exists") as mock_exists,
            patch("os.makedirs") as mock_makedirs,
            patch("wcgw.client.tools.get_repo_context") as mock_get_context,
        ):
            # Configure mocks
            mock_exists.return_value = True
            mock_get_context.return_value = (self.repo_context, self.test_workspace)

            # Create CodeWriterMode instance
            mode = CodeWriterMode(allowed_commands="all", allowed_globs=["*.py"])

            # Call initialize with CodeWriterMode
            result = initialize(
                any_workspace_path=self.test_workspace,
                read_files_=[],
                task_id_to_resume="",
                max_tokens=None,
                mode=mode,
            )

            # Verify repo context is included in output
            expected_context = f"---\n# Workspace structure\n{self.repo_context}\n---\n"
            self.assertIn(expected_context, result)

    def test_initialize_with_read_files(self):
        """Test initialize with file reading"""
        # Create a test file
        test_file = os.path.join(self.test_workspace, "test.txt")
        os.makedirs(os.path.dirname(test_file), exist_ok=True)
        with open(test_file, "w") as f:
            f.write("test content")

        with (
            patch("os.path.exists") as mock_exists,
            patch("wcgw.client.tools.read_files") as mock_read_files,
            patch("wcgw.client.tools.get_repo_context") as mock_get_context,
        ):
            mock_exists.return_value = True
            mock_get_context.return_value = (self.repo_context, self.test_workspace)
            test_file_path = os.path.join(self.test_workspace, "test.txt")
            mock_read_files.return_value = f"\n``` {test_file_path}\ntest content\n```"

            # Call initialize with read_files
            result = initialize(
                any_workspace_path=self.test_workspace,
                read_files_=["test.txt"],  # Relative path
                task_id_to_resume="",
                max_tokens=None,
                mode=Modes.wcgw,
            )

            # Verify read_files was called with correct path
            mock_read_files.assert_called_once_with([test_file_path], None)

            # Verify file content is included
            expected_content = (
                f"---\n# Requested files\n\n``` {test_file_path}\ntest content\n```"
            )
            self.assertIn(expected_content, result)

    def test_initialize_architect_mode(self):
        """Test initialize with architect mode"""
        # Call initialize with architect mode
        result = initialize(
            any_workspace_path="",
            read_files_=[],
            task_id_to_resume="",
            max_tokens=None,
            mode=Modes.architect,
        )

        # Verify architect mode text is included
        self.assertIn("not allowed to edit", result.lower())
        self.assertIn("read-only commands", result.lower())

    def test_load_bash_state(self):
        """Test loading bash state from task memory"""

        mock_load_memory = MagicMock()
        mock_load_memory.return_value = (
            self.test_workspace,
            "test_memory",
            {
                "bash_command_mode": {
                    "bash_mode": "normal_mode",
                    "allowed_commands": "all",
                },
                "file_edit_mode": {"allowed_globs": "all"},
                "write_if_empty_mode": {"allowed_globs": "all"},
                "whitelist_for_overwrite": [],
                "mode": "wcgw",
            },
        )

        with (
            patch("wcgw.client.tools.load_memory", mock_load_memory),
            patch("os.path.exists") as mock_exists,
        ):
            mock_exists.return_value = True

            result = initialize(
                any_workspace_path="",
                read_files_=[],
                task_id_to_resume="test_task",
                max_tokens=None,
                mode=Modes.wcgw,
            )

            # Verify task memory was loaded and state updated
            self.assertIn("Following is the retrieved task:\ntest_memory", result)

    def test_load_bash_state_non_wcgw_mode(self):
        """Test loading bash state when not in wcgw mode"""
        mock_load_memory = MagicMock()
        mock_load_memory.return_value = (
            self.test_workspace,
            "test_memory",
            {
                "bash_command_mode": {
                    "bash_mode": "normal_mode",
                    "allowed_commands": "all",
                },
                "file_edit_mode": {"allowed_globs": "all"},
                "write_if_empty_mode": {"allowed_globs": "all"},
                "whitelist_for_overwrite": [],
                "mode": "code_writer",
            },
        )

        with (
            patch("wcgw.client.tools.load_memory", mock_load_memory),
            patch("os.path.exists") as mock_exists,
        ):
            mock_exists.return_value = True

            # Call initialize with code_writer mode
            code_writer_mode = CodeWriterMode(
                allowed_commands="all", allowed_globs=["*.py"]
            )

            result = initialize(
                any_workspace_path="",
                read_files_=[],
                task_id_to_resume="test_task",
                max_tokens=None,
                mode=code_writer_mode,
            )

            # Verify task memory was still loaded
            self.assertIn("Following is the retrieved task:\ntest_memory", result)

    def test_load_bash_state_error(self):
        """Test handling state loading failures"""

        mock_load_memory = MagicMock()
        mock_load_memory.return_value = (
            self.test_workspace,
            "test_memory",
            {
                "bash_command_mode": {
                    "bash_mode": "invalid_mode",
                    "allowed_commands": "all",
                },
                "file_edit_mode": {"allowed_globs": "all"},
                "write_if_empty_mode": {"allowed_globs": "all"},
                "whitelist_for_overwrite": [],
                "mode": "invalid_mode",
            },  # Invalid mode values will cause ValueError
        )

        with (
            patch("wcgw.client.tools.load_memory", mock_load_memory),
            patch("os.path.exists") as mock_exists,
            patch("wcgw.client.tools.console") as mock_console,
            patch("wcgw.client.tools.get_repo_context") as mock_get_context,
            patch("wcgw.client.tools.BashState.parse_state") as mock_parse_state,
        ):
            mock_exists.return_value = True
            mock_get_context.return_value = ("test_context", self.test_workspace)
            mock_parse_state.side_effect = ValueError("Invalid state")

            result = initialize(
                any_workspace_path="",
                read_files_=[],
                task_id_to_resume="test_task",
                max_tokens=None,
                mode=Modes.wcgw,
            )

            # Verify error was logged
            mock_console.print.assert_any_call(unittest.mock.ANY)  # Error traceback
            mock_console.print.assert_any_call("Error: couldn't load bash state")

            # Verify task memory was still loaded despite state error
            self.assertIn("Following is the retrieved task:\ntest_memory", result)
