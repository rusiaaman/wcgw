import base64
import json
import os
import unittest
from unittest.mock import MagicMock, mock_open, patch

from wcgw.client.tools import (
    BASH_STATE,
    ImageData,
    get_incremental_output,
    render_terminal_output,
    which_tool,
    which_tool_name,
)
from wcgw.types_ import BashCommand, BashInteraction, Keyboard, Mouse, WriteIfEmpty


class TestToolsExtended(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        from wcgw.client.tools import BASH_STATE, INITIALIZED, TOOL_CALLS, initialize

        global INITIALIZED, TOOL_CALLS
        INITIALIZED = False
        TOOL_CALLS = []
        BASH_STATE._is_in_docker = ""  # Reset Docker state without shell reset

        # Properly initialize tools for testing
        initialize(
            any_workspace_path="",
            read_files_=[],
            task_id_to_resume="",
            max_tokens=None,
            mode="wcgw",
        )

    def tearDown(self):
        from wcgw.client.tools import BASH_STATE, INITIALIZED, TOOL_CALLS

        global INITIALIZED, TOOL_CALLS
        INITIALIZED = False  # Reset initialization state
        TOOL_CALLS = []  # Clear tool calls
        try:
            BASH_STATE.reset_shell()  # Reset bash state
        except Exception as e:
            print(f"Warning: Failed to reset BASH_STATE: {e}")
        # Clean up any temporary files or directories
        if hasattr(self, "_saved_filepath") and os.path.exists(
            getattr(self, "_saved_filepath")
        ):
            os.remove(self._saved_filepath)

    def test_get_incremental_output(self):
        old_output = ["line1", "line2"]
        new_output = ["line1", "line2", "line3"]

        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, ["line3"])

        # Test with empty old output
        result = get_incremental_output([], new_output)
        self.assertEqual(result, new_output)

        # Test with completely different output
        result = get_incremental_output(["old"], ["new"])
        self.assertEqual(result, ["new"])

    def test_render_terminal_output(self):
        # Test with ANSI escape sequences
        terminal_output = "\x1b[32mGreen Text\x1b[0m\nNext Line"
        result = render_terminal_output(terminal_output)
        # Strip spaces since terminal width may vary
        result = [line.strip() for line in result]
        self.assertEqual(result, ["Green Text", "Next Line"])

        # Test with carriage returns
        terminal_output = "First\rSecond\nThird"
        result = render_terminal_output(terminal_output)
        self.assertTrue("Second" in result[0])

    def test_which_tool(self):
        # Test BashCommand
        cmd_json = json.dumps({"command": "ls"})
        result = which_tool(cmd_json)
        self.assertIsInstance(result, BashCommand)
        self.assertEqual(result.command, "ls")

        # Test BashInteraction
        interaction_json = json.dumps({"send_text": "input"})
        result = which_tool(interaction_json)
        self.assertIsInstance(result, BashInteraction)
        self.assertEqual(result.send_text, "input")

    def test_which_tool_name(self):
        # Test valid tool names
        self.assertEqual(which_tool_name("BashCommand"), BashCommand)
        self.assertEqual(which_tool_name("Mouse"), Mouse)
        self.assertEqual(which_tool_name("Keyboard"), Keyboard)

        # Test invalid tool name
        with self.assertRaises(ValueError):
            which_tool_name("InvalidTool")

        # Test pending state
        BASH_STATE.set_pending("test output")
        self.assertEqual(BASH_STATE.state, "pending")
        self.assertEqual(BASH_STATE.pending_output, "test output")

        # Test whitelist operations
        BASH_STATE.add_to_whitelist_for_overwrite("/test/path")
        self.assertIn("/test/path", BASH_STATE.whitelist_for_overwrite)

    def test_image_data(self):
        # Test ImageData model
        image = ImageData(media_type="image/png", data="base64data")
        self.assertEqual(image.media_type, "image/png")
        self.assertEqual(image.data, "base64data")
        self.assertEqual(image.dataurl, "data:image/png;base64,base64data")

    @patch("os.path.exists")
    @patch("os.path.isabs")
    @patch("builtins.open", new_callable=mock_open)
    def test_read_image_from_shell(self, mock_file, mock_isabs, mock_exists):
        from wcgw.client.tools import read_image_from_shell

        # Setup mocks
        mock_isabs.return_value = True
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = b"test_image_data"

        # Test regular file read
        result = read_image_from_shell("/test/image.png")
        self.assertIsInstance(result, ImageData)
        self.assertEqual(result.media_type, "image/png")
        self.assertEqual(result.data, base64.b64encode(b"test_image_data").decode())

        # Test non-existent file
        mock_exists.return_value = False
        with self.assertRaises(ValueError):
            read_image_from_shell("/nonexistent/image.png")

    @patch("wcgw.client.tools.default_enc")
    def test_get_context_for_errors(self, mock_enc):
        from wcgw.client.tools import get_context_for_errors

        # Setup mock tokenizer
        mock_enc.encode.return_value = [1, 2, 3]  # simulate tokens

        # Test basic context
        file_content = "line1\nline2\nline3\nline4\nline5"
        errors = [(2, 0)]  # Error on line 2
        result = get_context_for_errors(errors, file_content, max_tokens=100)
        self.assertIn("line2", result)
        self.assertIn("```", result)

        # Test token limit exceeded
        mock_enc.encode.return_value = [i for i in range(200)]  # many tokens
        result = get_context_for_errors(errors, file_content, max_tokens=10)
        self.assertEqual(result, "Please re-read the file to understand the context")

    @patch("os.path.exists")
    @patch("os.path.isabs")
    @patch("pathlib.Path.open")
    @patch("pathlib.Path.mkdir")
    def test_write_file(self, mock_mkdir, mock_path_open, mock_isabs, mock_exists):
        from wcgw.client.tools import BASH_STATE, write_file

        # Setup mocks
        mock_isabs.return_value = True
        mock_exists.return_value = False
        mock_file = mock_open()
        mock_path_open.return_value.__enter__ = mock_file
        mock_path_open.return_value.__exit__ = MagicMock()

        # Test successful write
        test_file = WriteIfEmpty(
            file_path="/test/file.py", file_content="print('test')"
        )
        result = write_file(test_file, error_on_exist=True, max_tokens=100)
        self.assertIn("Success", result)

        # Test writing to existing file with error_on_exist=True and not in whitelist
        mock_exists.return_value = True
        BASH_STATE.whitelist_for_overwrite.clear()  # Clear whitelist
        test_file_new = WriteIfEmpty(
            file_path="/test/another_file.py",  # Use a different file not in whitelist
            file_content="print('test')",
        )
        with patch("pathlib.Path.read_text") as mock_read_text:
            mock_read_text.return_value = "existing content"
            result = write_file(test_file_new, error_on_exist=True, max_tokens=100)
            self.assertIn("Error: can't write to existing file", result)

        # Test with relative path
        mock_isabs.return_value = False
        result = write_file(test_file, error_on_exist=True, max_tokens=100)
        self.assertIn("Failure: file_path should be absolute path", result)

    def test_is_status_check(self):
        from wcgw.client.tools import is_status_check

        # Test with Enter special key
        interaction = BashInteraction(send_specials=["Enter"])
        self.assertTrue(is_status_check(interaction))

        # Test with ascii code 10 (newline)
        interaction = BashInteraction(send_ascii=[10])
        self.assertTrue(is_status_check(interaction))

        # Test with other interaction
        interaction = BashInteraction(send_text="hello")
        self.assertFalse(is_status_check(interaction))

        # Test with BashCommand
        cmd = BashCommand(command="ls")
        self.assertFalse(is_status_check(cmd))

    @patch("pexpect.spawn")
    def test_start_shell(self, mock_spawn):
        from wcgw.client.tools import PROMPT, start_shell

        # Setup mock shell
        mock_shell = MagicMock()
        mock_spawn.return_value = mock_shell

        # Test successful shell start
        shell = start_shell(is_restricted_mode=False, initial_dir="/")
        self.assertEqual(shell, mock_shell)

        # Verify shell initialization
        self.assertEqual(mock_shell.expect.call_count, 4)  # 4 setup commands
        mock_shell.sendline.assert_any_call(f"export PROMPT_COMMAND= PS1={PROMPT}")
        mock_shell.sendline.assert_any_call("stty -icanon -echo")
        mock_shell.sendline.assert_any_call("set +o pipefail")
        mock_shell.sendline.assert_any_call("export GIT_PAGER=cat PAGER=cat")

        # Test restricted mode
        mock_shell.reset_mock()
        shell = start_shell(is_restricted_mode=True, initial_dir="/")
        self.assertEqual(shell, mock_shell)

    def test_save_out_of_context(self):
        from wcgw.client.tools import save_out_of_context

        # Test saving content
        content = "Test content"
        suffix = ".txt"
        filepath = save_out_of_context(content, suffix)

        # Verify file was created and content saved
        self.assertTrue(os.path.exists(filepath))
        with open(filepath, "r") as f:
            saved_content = f.read()
            self.assertEqual(saved_content, content)

        # Cleanup
        os.remove(filepath)

    @patch("wcgw.client.tools.get_tool_output")
    def test_which_tool_errors(self, mock_get_tool_output):
        from wcgw.client.tools import which_tool

        # Test with invalid JSON
        with self.assertRaises(json.JSONDecodeError):
            which_tool("invalid json")

    @patch("os.system")
    @patch("tempfile.TemporaryDirectory")
    def test_write_file_docker(self, mock_temp_dir, mock_system):
        from wcgw.client.tools import BASH_STATE, write_file

        # Setup Docker environment
        BASH_STATE.set_in_docker("test_container")

        # Setup mocks
        mock_temp_dir.return_value.__enter__.return_value = "/tmp/test"
        mock_system.return_value = 0

        # Test writing in Docker environment
        test_file = WriteIfEmpty(
            file_path="/test/file.py", file_content="print('test')"
        )
        result = write_file(test_file, error_on_exist=False, max_tokens=100)
        self.assertIn("Success", result)

        # Test Docker command failure
        mock_system.return_value = 1
        result = write_file(test_file, error_on_exist=False, max_tokens=100)
        self.assertIn("Error: Write failed with code", result)

    @patch("wcgw.client.tools.command_run")
    def test_read_files_docker(self, mock_command_run):
        from wcgw.client.tools import BASH_STATE, DisableConsole, read_files

        # Setup mocks and test environment
        console = DisableConsole()
        BASH_STATE.set_in_docker("test_container")
        mock_command_run.return_value = (0, "file content", "")

        with patch("wcgw.client.tools.read_file") as mock_read_file:
            mock_read_file.return_value = ("file content", False, 10)

            # Test file read
            result = read_files(["/test/file.py"], max_tokens=100)
            self.assertIn("file content", result)

            # Cleanup
            BASH_STATE._is_in_docker = ""

        # Test read failure
        mock_command_run.return_value = (1, "", "error message")
        with patch("os.path.exists", return_value=False):
            result = read_files(["/test/nonexistent.py"], max_tokens=100)
        self.assertIn("file /test/nonexistent.py does not exist", result)

        # Reset Docker state
        BASH_STATE._is_in_docker = ""

    @patch("wcgw.client.tools.get_tool_output")
    def test_execute_bash_interaction(self, mock_get_tool):
        from wcgw.client.tools import BashInteraction, execute_bash

        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value.ids = [1, 2, 3]

        # Test sending special keys
        interaction = BashInteraction(
            send_specials=[
                "Enter",
                "Key-up",
                "Key-down",
                "Key-left",
                "Key-right",
                "Ctrl-c",
                "Ctrl-d",
                "Ctrl-z",
            ],
        )
        result, _ = execute_bash(
            mock_tokenizer, interaction, max_tokens=100, timeout_s=1
        )
        self.assertIsInstance(result, str)

        # Test sending ASCII characters
        interaction = BashInteraction(
            send_ascii=[97, 98, 99],  # 'abc'
        )
        result, _ = execute_bash(
            mock_tokenizer, interaction, max_tokens=100, timeout_s=1
        )
        self.assertIsInstance(result, str)

        # Test malformed interaction
        interaction = BashInteraction(
            send_text=None, send_ascii=None, send_specials=None
        )
        result, _ = execute_bash(
            mock_tokenizer, interaction, max_tokens=100, timeout_s=1
        )
        self.assertIn("Failure", result)

    @patch("wcgw.client.tools.check_syntax")
    @patch("os.system")
    def test_write_file_with_syntax_check(self, mock_system, mock_check):
        from wcgw.client.tools import write_file

        # Setup mocks
        mock_error = MagicMock()
        mock_error.description = "Invalid syntax"
        mock_error.errors = [(1, 0)]
        mock_check.return_value = mock_error
        mock_system.return_value = 0

        # Test file write with syntax error
        test_file = WriteIfEmpty(
            file_path="/test/file.py", file_content="invalid python code"
        )

        with patch("pathlib.Path.open", mock_open()):
            with patch("pathlib.Path.mkdir"):
                with patch("os.path.exists", return_value=False):
                    with patch("os.path.isabs", return_value=True):
                        result = write_file(
                            test_file, error_on_exist=True, max_tokens=100
                        )
                        self.assertIn("Success", result)
                        self.assertIn("syntax errors", result)
                        self.assertIn("Invalid syntax", result)

    @patch("wcgw.client.tools.read_image_from_shell")
    @patch("wcgw.client.tools.execute_bash")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.open", new_callable=mock_open)
    def test_get_tool_output_file_operations(
        self, mock_file, mock_mkdir, mock_execute_bash, mock_read_image
    ):
        """Test get_tool_output function with file operation tools"""
        from wcgw.client.tools import get_tool_output

        mock_enc = MagicMock()
        mock_loop_call = MagicMock()

        # Test ReadImage tool
        mock_read_image.return_value = ImageData(
            media_type="image/png", data="test_data"
        )
        result, cost = get_tool_output(
            {"file_path": "/test/image.png"},
            mock_enc,
            1.0,
            mock_loop_call,
            100,
        )
        self.assertIsInstance(result[0], ImageData)
        self.assertEqual(result[0].media_type, "image/png")

        # Test WriteIfEmpty tool
        result, cost = get_tool_output(
            {
                "file_path": "/test/file.txt",
                "file_content": "test content",
            },
            mock_enc,
            1.0,
            mock_loop_call,
            100,
        )
        self.assertTrue(isinstance(result[0], str))

    @patch("wcgw.client.tools.run_computer_tool")
    def test_get_tool_output_computer_interactions(self, mock_run_computer):
        """Test get_tool_output function with computer interaction tools"""
        from wcgw.client.tools import BASH_STATE, get_tool_output

        mock_enc = MagicMock()
        mock_loop_call = MagicMock()

        # Setup mock return value for computer tool
        mock_run_computer.return_value = ("Tool output", "screenshot_data")

        # Test Mouse tool
        result, cost = get_tool_output(
            {
                "action": {"button_type": "left_click"},
            },
            mock_enc,
            1.0,
            mock_loop_call,
            100,
        )
        self.assertEqual(len(result), 2)  # Output string and screenshot
        self.assertTrue(isinstance(result[0], str))

        # Test Keyboard tool with GetScreenInfo
        BASH_STATE.set_in_docker("test_container")
        result, cost = get_tool_output(
            {"action": "type", "text": "test input"},
            mock_enc,
            1.0,
            mock_loop_call,
            100,
        )
        self.assertEqual(len(result), 2)
        BASH_STATE._is_in_docker = ""

    @patch("wcgw.client.tools.take_help_of_ai_assistant")
    def test_get_tool_output_ai_assistant(self, mock_ai_helper):
        """Test get_tool_output function with AI Assistant tool"""
        from wcgw.client.tools import get_tool_output

        mock_enc = MagicMock()
        mock_loop_call = MagicMock()
        mock_ai_helper.return_value = ("AI response", 0.1)

        # Test AIAssistant tool
        result, cost = get_tool_output(
            {
                "instruction": "test instruction",
                "desired_output": "test output",
            },
            mock_enc,
            1.0,
            mock_loop_call,
            100,
        )
        self.assertEqual(result[0], "AI response")
        self.assertEqual(cost, 0.1)

    def test_get_tool_output_invalid_tool(self):
        """Test get_tool_output function with invalid tool"""
        from wcgw.client.tools import get_tool_output

        mock_enc = MagicMock()
        mock_loop_call = MagicMock()

        # Test with None
        with self.assertRaises(ValueError) as cm:
            get_tool_output(None, mock_enc, 1.0, mock_loop_call, 100)
        self.assertEqual(str(cm.exception), "Unknown tool: None")

        # Test with invalid tool type
        with self.assertRaises(ValueError) as cm:
            get_tool_output(123, mock_enc, 1.0, mock_loop_call, 100)

        # Test with empty dict
        result, cost = get_tool_output({}, mock_enc, 1.0, mock_loop_call, 100)
        self.assertIn("Failure:", result[0])
        self.assertEqual(cost, 0)

    def test_get_tool_output_exception_handling(self):
        """Test error handling in get_tool_output"""
        from wcgw.client.tools import get_tool_output

        mock_enc = MagicMock()
        mock_loop_call = MagicMock()

        # Create a write tool for testing with a relative path
        # This should raise a validation error without needing to mock write_file
        write_tool = WriteIfEmpty(file_path="relative/path", file_content="test")

        # Test: function should catch the validation error and return an error message
        result, cost = get_tool_output(write_tool, mock_enc, 1.0, mock_loop_call, 100)

        # Verify the error is handled gracefully
        self.assertEqual(cost, 0)  # Cost should be 0 when there's an error
        self.assertTrue(isinstance(result, list))  # Result should be a list
        self.assertEqual(len(result), 1)  # Should have one item
        self.assertTrue(isinstance(result[0], str))  # Should be a string message
        # Error message should mention the path issue
        self.assertIn("file_path should be absolute path", result[0])


if __name__ == "__main__":
    unittest.main()
