import json
import unittest
from unittest.mock import MagicMock, patch

from wcgw.client.tools import (
    BASH_STATE,
    ensure_no_previous_output,
    get_tool_output,
    truncate_if_over,
    which_tool,
    which_tool_name,
)
from wcgw.types_ import (
    BashCommand,
    BashInteraction,
    Keyboard,
    Mouse,
    WriteIfEmpty,
)


class TestToolsValidation(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        from wcgw.client.tools import BASH_STATE, initialize

        BASH_STATE.reset_shell()
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
        except:
            pass

    def test_ensure_no_previous_output_decorator(self):
        """Test ensure_no_previous_output decorator"""

        @ensure_no_previous_output
        def test_func():
            return "success"

        # Test when no previous output
        BASH_STATE.set_repl()
        result = test_func()
        self.assertEqual(result, "success")

        # Test when previous output exists
        BASH_STATE.set_pending("previous output")
        with self.assertRaises(ValueError) as context:
            test_func()
        self.assertIn("A command is already running", str(context.exception))

    def test_truncate_if_over(self):
        """Test truncate_if_over function"""
        mock_enc = MagicMock()
        mock_enc.encode = MagicMock()
        mock_enc.decode = MagicMock()

        with patch("wcgw.client.tools.default_enc", mock_enc):
            # Test with content under limit
            content = "short content"
            mock_enc.encode.return_value = MagicMock(ids=list(range(5)))  # Under limit
            result = truncate_if_over(content, max_tokens=200)
            self.assertEqual(
                result, content
            )  # Should return original content when under limit
            self.assertEqual(
                mock_enc.decode.call_count, 0
            )  # Decode shouldn't be called

            # Test with content over limit
            long_content = "very long content" * 100
            mock_encoding = MagicMock()
            mock_encoding.ids = list(range(200))  # Over limit
            mock_encoding.__len__.return_value = 200  # Make len(tokens) return 200
            mock_enc.encode.return_value = mock_encoding
            mock_enc.decode.return_value = "truncated content"

            result = truncate_if_over(long_content, max_tokens=50)
            # In truncate_if_over: max(0, max_tokens - 100) = max(0, 50-100)
            truncated_ids = []  # Since 50-100 = -50, max(0, -50) = 0
            mock_enc.decode.assert_called_once_with(truncated_ids)
            self.assertEqual(result, "truncated content\n(...truncated)")

            # Test with None max_tokens
            result = truncate_if_over(long_content, max_tokens=None)
            self.assertEqual(result, long_content)

            # Test with no token limit
            result = truncate_if_over(long_content, max_tokens=None)
            self.assertEqual(result, long_content)

    def test_which_tool(self):
        """Test which_tool function"""
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

        # Test invalid JSON
        with self.assertRaises(json.JSONDecodeError):
            which_tool("invalid json")

        # Test invalid tool type
        invalid_json = json.dumps({"type": "InvalidTool"})
        with self.assertRaises(ValueError):
            which_tool(invalid_json)

    def test_which_tool_name(self):
        """Test which_tool_name function"""
        # Test valid tool names
        self.assertEqual(which_tool_name("BashCommand"), BashCommand)
        self.assertEqual(which_tool_name("BashInteraction"), BashInteraction)
        self.assertEqual(which_tool_name("WriteIfEmpty"), WriteIfEmpty)
        self.assertEqual(which_tool_name("Mouse"), Mouse)
        self.assertEqual(which_tool_name("Keyboard"), Keyboard)

        # Test invalid tool name
        with self.assertRaises(ValueError):
            which_tool_name("InvalidTool")

    @patch("wcgw.client.tools.execute_bash")
    def test_get_tool_output(self, mock_execute_bash):
        """Test get_tool_output function"""
        mock_enc = MagicMock()
        mock_loop_call = MagicMock()

        # Test BashCommand
        mock_execute_bash.return_value = ("command output", 0)
        result, cost = get_tool_output(
            BashCommand(command="ls"), mock_enc, 1.0, mock_loop_call, 100
        )
        self.assertEqual(result[0], "command output")
        self.assertEqual(cost, 0)

        # Test WriteIfEmpty
        test_file = WriteIfEmpty(file_path="/test/file.txt", file_content="test")
        with patch("wcgw.client.tools.write_file") as mock_write:
            mock_write.return_value = "Success"
            result, cost = get_tool_output(
                test_file, mock_enc, 1.0, mock_loop_call, 100
            )
            self.assertEqual(result[0], "Success")
            self.assertEqual(cost, 0)

        # Test error handling
        with self.assertRaises(ValueError):
            get_tool_output({"type": "InvalidTool"}, mock_enc, 1.0, mock_loop_call, 100)

    def test_get_tool_output_exceptions(self):
        """Test get_tool_output exception handling"""
        mock_enc = MagicMock()
        mock_loop_call = MagicMock()

        # Test with relative path in WriteIfEmpty
        test_file = WriteIfEmpty(file_path="relative/path.txt", file_content="test")
        result, cost = get_tool_output(test_file, mock_enc, 1.0, mock_loop_call, 100)
        self.assertIn("file_path should be absolute path", result[0])
        self.assertEqual(cost, 0)

        # Test with invalid tool type
        with self.assertRaises(ValueError) as context:
            get_tool_output({"type": "InvalidTool"}, mock_enc, 1.0, mock_loop_call, 100)
        self.assertIn("validation errors for union", str(context.exception))

    def test_get_tool_output_computer_tools(self):
        """Test get_tool_output with computer interaction tools"""
        mock_enc = MagicMock()
        mock_loop_call = MagicMock()

        # Test Mouse tool
        with patch("wcgw.client.tools.run_computer_tool") as mock_run:
            mock_run.return_value = ("Mouse clicked", "screenshot_data")
            result, cost = get_tool_output(
                Mouse(action={"button_type": "left_click"}),
                mock_enc,
                1.0,
                mock_loop_call,
                100,
            )
            self.assertEqual(result[0], "Mouse clicked")
            self.assertTrue(hasattr(result[1], "media_type"))
            self.assertEqual(result[1].media_type, "image/png")
            self.assertEqual(result[1].data, "screenshot_data")

        # Test Keyboard tool
        with patch("wcgw.client.tools.run_computer_tool") as mock_run:
            mock_run.return_value = ("Keys typed", "screenshot_data")
            result, cost = get_tool_output(
                Keyboard(action="type", text="test"), mock_enc, 1.0, mock_loop_call, 100
            )
            self.assertEqual(result[0], "Keys typed")
            self.assertTrue(hasattr(result[1], "media_type"))
            self.assertEqual(result[1].media_type, "image/png")
            self.assertEqual(result[1].data, "screenshot_data")

    @patch("wcgw.client.tools.run_computer_tool")
    def test_get_tool_output_error_propagation(self, mock_run):
        """Test error propagation in get_tool_output"""
        mock_enc = MagicMock()
        mock_loop_call = MagicMock()

        # Test error propagation from computer tools
        mock_run.return_value = (
            "Error: Computer tool error",
            None,
        )  # Return error style tuple instead of raising
        result, cost = get_tool_output(
            Mouse(action={"button_type": "left_click"}),
            mock_enc,
            1.0,
            mock_loop_call,
            100,
        )
        # When error happens, first element should be error string, second element should be None
        self.assertEqual(result[0], "Error: Computer tool error")
        self.assertEqual(cost, 0)

        # Test error propagation from bash execution
        with patch("wcgw.client.tools.execute_bash") as mock_bash:
            mock_bash.return_value = (
                "Error: Bash error",
                0,
            )  # Return error as string, not as exception
            result, cost = get_tool_output(
                BashCommand(command="ls"), mock_enc, 1.0, mock_loop_call, 100
            )
            self.assertEqual(result[0], "Error: Bash error")
            self.assertEqual(cost, 0)
            self.assertIn("Bash error", result[0])
            self.assertEqual(cost, 0)
