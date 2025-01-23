"""Tests for initialize functionality in tools.py"""

import os
import shutil
import unittest
from unittest.mock import patch, MagicMock

from wcgw.client.tools import initialize, BASH_STATE
from wcgw.types_ import Modes, CodeWriterMode


@patch('wcgw.client.tools.render_terminal_output', return_value=['test_output'])
@patch('wcgw.client.tools.start_shell')
@patch('wcgw.client.tools._ensure_env_and_bg_jobs', return_value=0)
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
        
    def test_load_memory_error(self, mock_ensure_env, mock_start_shell, mock_render):
        # Configure shell mock
        mock_shell = mock_start_shell.return_value
        mock_shell.before = "test"
        mock_shell.expect.return_value = 0
        mock_shell.linesep = "\n"
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
                mode=Modes.wcgw
            )
            
            # Verify error message is included in output
            self.assertIn('Error: Unable to load task with ID "test_task_id"', result)
            
            # Verify load_memory was called with correct parameters
            mock_load.assert_called_once_with(
                "test_task_id",
                None,  # max_tokens
                unittest.mock.ANY,  # encode lambda
                unittest.mock.ANY   # decode lambda
            )
            
    def test_workspace_path_exists(self, mock_ensure_env, mock_start_shell, mock_render):
        """Test initialize handling when workspace path exists"""
        # Configure shell mock
        mock_shell = mock_start_shell.return_value
        mock_shell.before = "test"
        mock_shell.expect.return_value = 0
        mock_shell.linesep = "\n"
        
        with patch("os.path.exists") as mock_exists, \
             patch("os.makedirs") as mock_makedirs, \
             patch("wcgw.client.tools.get_repo_context") as mock_get_context:
            
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
                mode=mode
            )
            
            # Verify repo context is included in output
            expected_context = f"---\n# Workspace structure\n{self.repo_context}\n---\n"
            self.assertIn(expected_context, result)
            
    def test_initialize_with_read_files(self, mock_ensure_env, mock_start_shell, mock_render):
        """Test initialize with file reading"""
        mock_shell = mock_start_shell.return_value
        mock_shell.before = "test"
        mock_shell.expect.return_value = 0
        mock_shell.linesep = "\n"
        
        # Create a test file
        test_file = os.path.join(self.test_workspace, "test.txt")
        os.makedirs(os.path.dirname(test_file), exist_ok=True)
        with open(test_file, "w") as f:
            f.write("test content")
        
        with patch("os.path.exists") as mock_exists, \
             patch("wcgw.client.tools.get_repo_context") as mock_get_context:
            
            mock_exists.return_value = True
            mock_get_context.return_value = (self.repo_context, self.test_workspace)
            
            # Call initialize with read_files
            result = initialize(
                any_workspace_path=self.test_workspace,
                read_files_=["test.txt"],  # Relative path
                task_id_to_resume="",
                max_tokens=None,
                mode=Modes.wcgw
            )
            
            # Verify file content is included
            expected_content = f"---\n# Requested files\n\n``` {os.path.join(self.test_workspace, 'test.txt')}\ntest content\n```"
            self.assertIn(expected_content, result)
            
    def test_reset_shell(self, mock_ensure_env, mock_start_shell, mock_render):
        """Test shell reset functionality"""
        mock_shell = mock_start_shell.return_value
        mock_shell.before = "test"
        mock_shell.expect.return_value = 0
        mock_shell.linesep = "\n"
        
        with patch("wcgw.client.tools.get_status", return_value="\nstatus = ready\ncwd = /test") as mock_status:
            from wcgw.client.tools import reset_shell, BASH_STATE
            
            # Add close method to mock shell
            mock_shell.close = MagicMock()
            
            # Reset the shell
            result = BASH_STATE.reset_shell()
            
            # Call the reset function
            result = reset_shell()
            
            # Verify shell was reset
            self.assertEqual(result, "Reset successful\nstatus = ready\ncwd = /test")
            mock_start_shell.assert_called()  # New shell created
            mock_shell.close.assert_called_with(True)  # Old shell closed
            
    def test_initialize_architect_mode(self, mock_ensure_env, mock_start_shell, mock_render):
        """Test initialize with architect mode"""
        mock_shell = mock_start_shell.return_value
        mock_shell.before = "test"
        mock_shell.expect.return_value = 0
        mock_shell.linesep = "\n"
        
        with patch("wcgw.client.tools.ARCHITECT_PROMPT", "architect_prompt_text"):
            # Call initialize with architect mode
            result = initialize(
                any_workspace_path="",
                read_files_=[],
                task_id_to_resume="",
                max_tokens=None,
                mode=Modes.architect
            )
            
            # Verify architect mode prompt is included
            self.assertIn("architect_prompt_text", result)

    def test_load_bash_state(self, mock_ensure_env, mock_start_shell, mock_render):
        """Test loading bash state from task memory"""
        # Configure shell mock
        mock_shell = mock_start_shell.return_value
        mock_shell.before = "test"
        mock_shell.expect.return_value = 0
        mock_shell.linesep = "\n"

        mock_load_memory = MagicMock()
        mock_load_memory.return_value = (self.test_workspace, "test_memory", {
            "bash_command_mode": {"bash_mode": "normal_mode", "allowed_commands": "all"},
            "file_edit_mode": {"allowed_globs": "all"},
            "write_if_empty_mode": {"allowed_globs": "all"},
            "whitelist_for_overwrite": [],
            "mode": "wcgw"
        })

        with patch("wcgw.client.tools.load_memory", mock_load_memory), \
             patch("os.path.exists") as mock_exists:

            mock_exists.return_value = True

            result = initialize(
                any_workspace_path="",
                read_files_=[],
                task_id_to_resume="test_task",
                max_tokens=None,
                mode=Modes.wcgw
            )

            # Verify task memory was loaded and state updated
            self.assertIn("Following is the retrieved task:\ntest_memory", result)
            
    def test_load_bash_state_non_wcgw_mode(self, mock_ensure_env, mock_start_shell, mock_render):
        """Test loading bash state when not in wcgw mode"""
        # Configure shell mock
        mock_shell = mock_start_shell.return_value
        mock_shell.before = "test"
        mock_shell.expect.return_value = 0
        mock_shell.linesep = "\n"
        
        mock_load_memory = MagicMock()
        mock_load_memory.return_value = (self.test_workspace, "test_memory", {
            "bash_command_mode": {"bash_mode": "normal_mode", "allowed_commands": "all"},
            "file_edit_mode": {"allowed_globs": "all"},
            "write_if_empty_mode": {"allowed_globs": "all"},
            "whitelist_for_overwrite": [],
            "mode": "code_writer"
        })
        
        with patch("wcgw.client.tools.load_memory", mock_load_memory), \
             patch("os.path.exists") as mock_exists:
                
            mock_exists.return_value = True
            
            # Call initialize with code_writer mode
            code_writer_mode = CodeWriterMode(allowed_commands="all", allowed_globs=["*.py"])
            
            result = initialize(
                any_workspace_path="",
                read_files_=[],
                task_id_to_resume="test_task",
                max_tokens=None,
                mode=code_writer_mode
            )
            
            # Verify task memory was still loaded
            self.assertIn("Following is the retrieved task:\ntest_memory", result)
            
    def test_load_bash_state_error(self, mock_ensure_env, mock_start_shell, mock_render):
        """Test handling state loading failures"""
        # Configure shell mock
        mock_shell = mock_start_shell.return_value
        mock_shell.before = "test"
        mock_shell.expect.return_value = 0
        mock_shell.linesep = "\n"
        
        mock_load_memory = MagicMock()
        mock_load_memory.return_value = (
            self.test_workspace, 
            "test_memory", 
            {
                "bash_command_mode": {"bash_mode": "invalid_mode", "allowed_commands": "all"},
                "file_edit_mode": {"allowed_globs": "all"},
                "write_if_empty_mode": {"allowed_globs": "all"},
                "whitelist_for_overwrite": [],
                "mode": "invalid_mode"
            }  # Invalid mode values will cause ValueError
        )
        
        with patch("wcgw.client.tools.load_memory", mock_load_memory), \
             patch("os.path.exists") as mock_exists, \
             patch("wcgw.client.tools.console") as mock_console, \
             patch("wcgw.client.tools.get_repo_context") as mock_get_context, \
             patch('wcgw.client.tools.BashState.parse_state') as mock_parse_state:

            mock_exists.return_value = True
            mock_get_context.return_value = ("test_context", self.test_workspace)
            mock_parse_state.side_effect = ValueError("Invalid state")

            result = initialize(
                any_workspace_path="",
                read_files_=[],
                task_id_to_resume="test_task",
                max_tokens=None,
                mode=Modes.wcgw
            )

            # Verify error was logged
            mock_console.print.assert_any_call(unittest.mock.ANY)  # Error traceback
            mock_console.print.assert_any_call("Error: couldn't load bash state")
            
            # Verify task memory was still loaded despite state error
            self.assertIn("Following is the retrieved task:\ntest_memory", result)