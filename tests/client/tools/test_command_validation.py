"""Tests for command validation functionality in tools.py"""

import json
import unittest
from unittest.mock import MagicMock, patch

from wcgw.client.tools import (
    BASH_STATE,
    get_status,
    is_status_check,
    update_repl_prompt,
    which_tool,
    which_tool_name,
)
from wcgw.types_ import (
    BashCommand,
    BashInteraction,
    Keyboard,
    Mouse,
)


class TestCommandValidation(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        BASH_STATE.reset_shell()

    def test_which_tool(self):
        """Test tool type determination"""
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
        with self.assertRaises(ValueError):
            which_tool(json.dumps({"type": "InvalidTool"}))

    def test_which_tool_name(self):
        """Test tool name mapping"""
        # Test valid tool names
        self.assertEqual(which_tool_name("BashCommand"), BashCommand)
        self.assertEqual(which_tool_name("BashInteraction"), BashInteraction)
        self.assertEqual(which_tool_name("Mouse"), Mouse)
        self.assertEqual(which_tool_name("Keyboard"), Keyboard)

        # Test invalid tool name
        with self.assertRaises(ValueError):
            which_tool_name("InvalidTool")

    def test_is_status_check(self):
        """Test status check detection"""
        # Test with Enter special key
        interaction = BashInteraction(send_specials=["Enter"])
        self.assertTrue(is_status_check(interaction))

        # Test with newline ASCII code
        interaction = BashInteraction(send_ascii=[10])
        self.assertTrue(is_status_check(interaction))

        # Test with other interaction types
        interaction = BashInteraction(send_text="hello")
        self.assertFalse(is_status_check(interaction))

        # Test with BashCommand
        command = BashCommand(command="ls")
        self.assertFalse(is_status_check(command))

    def test_update_repl_prompt(self):
        """Test REPL prompt updating"""
        with patch("wcgw.client.tools.BASH_STATE") as mock_state:
            mock_state.shell = MagicMock()
            mock_state.shell.before = "new_prompt"
            mock_state.shell.expect.return_value = 1

            # Test valid prompt update command
            result = update_repl_prompt("wcgw_update_prompt()")
            self.assertTrue(result)

            # Test invalid command
            result = update_repl_prompt("not_an_update_command")
            self.assertFalse(result)

    def test_get_status(self):
        """Test status reporting"""
        with patch("wcgw.client.tools.BASH_STATE") as mock_state:
            # Test pending state
            mock_state.state = "pending"
            mock_state.cwd = "/test/dir"
            mock_state.get_pending_for.return_value = "10 seconds"

            status = get_status()
            self.assertIn("status = still running", status)
            self.assertIn("running for = 10 seconds", status)
            self.assertIn("cwd = /test/dir", status)

            # Test completed state with background jobs
            mock_state.state = "repl"
            mock_state.update_cwd.return_value = "/test/dir2"
            with patch("wcgw.client.tools._ensure_env_and_bg_jobs", return_value=2):
                status = get_status()
                self.assertIn(
                    "status = process exited; 2 background jobs running", status
                )
                self.assertIn("cwd = /test/dir2", status)

            # Test completed state without background jobs
            mock_state.state = "repl"
            mock_state.update_cwd.return_value = "/test/dir3"
            with patch("wcgw.client.tools._ensure_env_and_bg_jobs", return_value=0):
                status = get_status()
                self.assertIn("status = process exited", status)
                self.assertNotIn("background jobs running", status)
                self.assertIn("cwd = /test/dir3", status)
