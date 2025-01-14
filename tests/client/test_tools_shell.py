import datetime
import unittest
from unittest.mock import MagicMock, call, patch

import pexpect

from wcgw.client import tools
from wcgw.client.tools import (
    BASH_STATE,
    _ensure_env_and_bg_jobs,
    _is_int,
    execute_bash,
    get_status,
    render_terminal_output,
    start_shell,
    update_repl_prompt,
)
from wcgw.types_ import BashCommand, BashInteraction


class TestToolsShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize mock tokenizer at class level to avoid recreation
        cls.mock_tokenizer = MagicMock()
        cls.mock_tokenizer.encode.return_value.ids = [1, 2, 3]
        cls.mock_tokenizer.decode.return_value = "decoded text"

    def setUp(self):
        # Save original global BASH_STATE fields
        self.orig_bash_state = BASH_STATE._state
        self.orig_is_docker = BASH_STATE._is_in_docker

        # Also save original PROMPT
        self.orig_prompt = tools.PROMPT
        # Set a test-specific prompt
        tools.PROMPT = "TEST_PROMPT>"

        # Create a mock shell for convenience
        self.mock_shell = MagicMock()
        self.mock_shell.send = MagicMock()
        self.mock_shell.sendintr = MagicMock()
        self.mock_shell.before = ""
        self.mock_shell.expect = MagicMock(return_value=0)

    def tearDown(self):
        # Restore all global states
        BASH_STATE._state = self.orig_bash_state
        BASH_STATE._is_in_docker = self.orig_is_docker
        tools.PROMPT = self.orig_prompt

    @patch("wcgw.client.tools.pexpect.spawn")
    @patch("wcgw.client.tools.os")
    def test_start_shell_error_handling(self, mock_os, mock_spawn):
        # Setup environment
        mock_os.environ = {"PATH": "/usr/bin"}
        mock_os.path.exists.return_value = True

        # Create mock shell with proper responses
        mock_shell = MagicMock()
        mock_shell.expect.return_value = 0
        mock_shell.before = ""
        mock_spawn.return_value = mock_shell

        # Test successful shell start with non-restricted mode
        shell = start_shell(is_restricted_mode=False, initial_dir="/")
        self.assertEqual(shell, mock_shell)

        # Verify shell initialization commands
        self.assertEqual(mock_shell.expect.call_count, 4)
        mock_shell.sendline.assert_any_call("stty -icanon -echo")
        mock_shell.sendline.assert_any_call("set +o pipefail")

        # Test error handling with fallback
        # Test error handling with fallback in both modes
        mock_spawn.side_effect = [Exception("Failed"), mock_shell]
        shell = start_shell(is_restricted_mode=False, initial_dir="/")
        self.assertEqual(shell, mock_shell)

        mock_spawn.side_effect = [Exception("Failed"), mock_shell]
        shell = start_shell(is_restricted_mode=True, initial_dir="/")
        self.assertEqual(shell, mock_shell)

    def test_is_int_validation(self):
        # Test various inputs for _is_int function
        self.assertTrue(_is_int("123"))
        self.assertTrue(_is_int("-456"))
        self.assertTrue(_is_int("0"))
        self.assertFalse(_is_int("abc"))
        self.assertFalse(_is_int("12.34"))
        self.assertFalse(_is_int(""))
        self.assertFalse(_is_int(" "))
        self.assertFalse(_is_int("\n"))

    # ---------------------------------------------------------------------------------
    # Test _ensure_env_and_bg_jobs
    # ---------------------------------------------------------------------------------
    @patch("wcgw.client.tools.PROMPT", new="TEST_PROMPT>")
    @patch("wcgw.client.tools.PROMPT_CONST", new="TEST_PROMPT>")
    @patch("wcgw.client.tools.TIMEOUT", new=1)  # Reduce waiting in tests
    def test_ensure_env_bg_jobs(self):
        """Test background jobs check and environment setup"""

        # Reuse self.mock_shell for scenarios 1 & 2 & 3
        mock_shell = self.mock_shell
        mock_shell.sendline = MagicMock()

        # Scenario 1: Normal output => "2"
        def setup_mock_expect_normal(pattern, timeout=None):
            outputs = getattr(
                setup_mock_expect_normal, "outputs", ["", "", "", "", "2"]
            )
            if outputs:
                mock_shell.before = outputs.pop(0)
            else:
                mock_shell.before = "2"
            return 0

        setup_mock_expect_normal.outputs = ["", "", "", "", "2"]
        mock_shell.expect = MagicMock(side_effect=setup_mock_expect_normal)

        result = _ensure_env_and_bg_jobs(mock_shell)
        self.assertEqual(result, 2)
        # 4 env setup lines + 1 "jobs | wc -l"
        self.assertEqual(mock_shell.sendline.call_count, 5)

        # Scenario 2: Invalid first => valid second
        def setup_mock_expect_recovery(pattern, timeout=None):
            outputs = getattr(
                setup_mock_expect_recovery, "outputs", ["", "", "", "", "invalid", "2"]
            )
            if outputs:
                mock_shell.before = outputs.pop(0)
            else:
                mock_shell.before = "2"
            return 0

        setup_mock_expect_recovery.outputs = ["", "", "", "", "invalid", "2"]
        mock_shell.reset_mock()
        mock_shell.expect = MagicMock(side_effect=setup_mock_expect_recovery)

        result = _ensure_env_and_bg_jobs(mock_shell)
        self.assertEqual(result, 2)
        self.assertEqual(mock_shell.sendline.call_count, 5)

        # Scenario 3: Persistent invalid => emulate final TIMEOUT
        def setup_mock_expect_persistent_invalid(pattern, timeout=None):
            mock_shell.before = "invalid"
            # We simulate a real shell timing out eventually:
            raise pexpect.TIMEOUT("Persistent invalid output")

        mock_shell.reset_mock()
        mock_shell.expect = MagicMock(side_effect=setup_mock_expect_persistent_invalid)
        with self.assertRaises(pexpect.TIMEOUT):
            _ensure_env_and_bg_jobs(mock_shell)

        # Scenario 4: Different PROMPT => returns None immediately, no calls
        new_shell = MagicMock()
        new_shell.sendline = MagicMock()
        new_shell.expect = MagicMock()

        with patch("wcgw.client.tools.PROMPT", new="DIFFERENT>"):
            result = _ensure_env_and_bg_jobs(new_shell)
            self.assertIsNone(result)
            # Because PROMPT != PROMPT_CONST, the function returns right away
            new_shell.expect.assert_not_called()
            new_shell.sendline.assert_not_called()

    # ---------------------------------------------------------------------------------
    # Test execute_bash with mock BASH_STATE
    # ---------------------------------------------------------------------------------
    @patch("wcgw.client.tools.BASH_STATE")
    def test_execute_bash_command(self, mock_bash_state):
        mock_shell = self.mock_shell
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.pending_output = ""
        mock_bash_state.update_cwd.return_value = "/test/dir"

        def mock_get_status():
            return "\n\nstatus = process exited\ncwd = /test/dir"

        with patch("wcgw.client.tools.get_status", side_effect=mock_get_status):
            # Test simple command
            command = BashCommand(command="echo test")
            self.mock_shell.before = "test output\n"
            output, cost = execute_bash(
                self.mock_tokenizer, command, max_tokens=100, timeout_s=1
            )
            self.assertIsInstance(output, str)
            self.assertIn("test output", output)
            self.assertEqual(cost, 0)

        # Test command with newline (should fail)
        command = BashCommand(command="echo test1\necho test2")
        with self.assertRaises(ValueError):
            execute_bash(self.mock_tokenizer, command, max_tokens=100, timeout_s=1)

        # Test command when process is pending
        mock_bash_state.state = "pending"
        with self.assertRaises(ValueError) as ctx:
            execute_bash(self.mock_tokenizer, command, max_tokens=100, timeout_s=1)
        self.assertIn("command is already running", str(ctx.exception).lower())

    @patch("wcgw.client.tools.PROMPT", new="TEST_PROMPT>")
    @patch("wcgw.client.tools.PROMPT_CONST", new="TEST_PROMPT>")
    @patch("wcgw.client.tools.BASH_STATE")
    @patch("wcgw.client.tools.pexpect")
    @patch(
        "wcgw.client.tools.get_status",
        return_value="\n\nstatus = process exited\ncwd = /test/dir",
    )
    def test_execute_bash_basic_interactions(
        self, mock_get_status, mock_pexpect, mock_bash_state
    ):
        """Test basic bash interactions and special keys"""
        mock_shell = MagicMock()
        mock_shell.before = ""
        mock_shell.send = MagicMock()
        mock_shell.sendintr = MagicMock()
        mock_shell.linesep = "\n"

        # Configure BASH_STATE
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.pending_output = ""
        mock_bash_state._state = "repl"
        mock_bash_state.set_repl = MagicMock()
        mock_bash_state.set_pending = MagicMock()

        mock_pexpect.TIMEOUT = pexpect.TIMEOUT

        # Test 1: Basic text input
        mock_shell.expect.return_value = 0
        interaction = BashInteraction(send_text="hello")
        output, cost = execute_bash(
            self.mock_tokenizer, interaction, max_tokens=100, timeout_s=0.1
        )
        mock_shell.send.assert_has_calls([call("hello"), call("\n")])
        self.assertEqual(mock_shell.expect.call_count, 1)
        self.assertEqual(cost, 0)

        # Test 2: Special keys
        mock_shell.reset_mock()
        mock_shell.expect.return_value = 0
        key_mappings = {
            "Key-up": "\033[A",
            "Key-down": "\033[B",
            "Key-left": "\033[D",
            "Key-right": "\033[C",
            "Enter": "\n",
            "Ctrl-c": None,  # sendintr()
            "Ctrl-d": None,  # sendintr()
            "Ctrl-z": "\x1a",
        }
        for key, expected_send in key_mappings.items():
            mock_shell.reset_mock()
            interaction = BashInteraction(send_specials=[key])
            output, cost = execute_bash(
                self.mock_tokenizer, interaction, max_tokens=100, timeout_s=0.1
            )
            if expected_send is None:
                mock_shell.sendintr.assert_called_once()
                self.assertEqual(mock_shell.send.call_count, 0)
            else:
                mock_shell.send.assert_called_once_with(expected_send)
                self.assertEqual(mock_shell.sendintr.call_count, 0)
            self.assertEqual(cost, 0)

        # Test 3: ASCII sequence
        mock_shell.reset_mock()
        interaction = BashInteraction(send_ascii=[65])  # 'A'
        output, cost = execute_bash(
            self.mock_tokenizer, interaction, max_tokens=100, timeout_s=0.1
        )
        mock_shell.send.assert_called_with("A")

        # Test 4: Invalid combos
        mock_shell.reset_mock()
        interaction = BashInteraction(send_text="test", send_ascii=[65])
        output, cost = execute_bash(
            self.mock_tokenizer, interaction, max_tokens=100, timeout_s=0.1
        )
        self.assertIn("Failure", output)
        self.assertEqual(cost, 0)

        # Test 5: Empty interaction
        mock_shell.reset_mock()
        interaction = BashInteraction()
        output, cost = execute_bash(
            self.mock_tokenizer, interaction, max_tokens=100, timeout_s=0.1
        )
        self.assertIn("Failure", output)
        self.assertEqual(cost, 0)

    @patch("wcgw.client.tools.PROMPT", new="TEST_PROMPT>")
    @patch("wcgw.client.tools.PROMPT_CONST", new="TEST_PROMPT>")
    @patch("wcgw.client.tools.BASH_STATE")
    @patch("wcgw.client.tools.pexpect")
    @patch(
        "wcgw.client.tools.get_status",
        return_value="\n\nstatus = process exited\ncwd = /test/dir",
    )
    def test_execute_bash_timeout_handling(
        self, mock_get_status, mock_pexpect, mock_bash_state
    ):
        """Test timeout handling in bash execution"""
        mock_shell = MagicMock()
        mock_shell.before = ""
        mock_shell.send = MagicMock()
        mock_shell.sendintr = MagicMock()
        mock_shell.linesep = "\n"

        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.pending_output = ""
        mock_bash_state._state = "repl"
        mock_bash_state.set_repl = MagicMock()
        mock_bash_state.set_pending = MagicMock()

        mock_pexpect.TIMEOUT = pexpect.TIMEOUT

        #
        # SCENARIO 1: Simulate a partial "timeout" by returning index=1 first call, then index=0 second call
        # This does NOT raise the pexpect.TIMEOUT exception in Python, but returns 1 => "matched" the TIMEOUT pattern
        #
        def mock_expect_timeout(patterns, timeout=0.1):
            call_count = getattr(mock_expect_timeout, "call_count", 0)
            setattr(mock_expect_timeout, "call_count", call_count + 1)

            if call_count == 0:
                # 1st call: partial output => matched second pattern => code logs partial text
                mock_shell.before = "initial output\n"
                mock_bash_state.set_pending(mock_shell.before)
                # Return 1 => we matched "pexpect.TIMEOUT" in the patterns
                return 1
            else:
                # 2nd call => matched the prompt
                mock_shell.before = "some final output\n"
                if isinstance(patterns, list) and "TEST_PROMPT>" in patterns:
                    mock_bash_state.set_repl()
                    return patterns.index("TEST_PROMPT>")
                return 0

        mock_expect_timeout.call_count = 0
        mock_shell.expect = MagicMock(side_effect=mock_expect_timeout)

        # Attempt a command with "basic timeout and retry" scenario
        interaction = BashInteraction(send_specials=["Enter"])
        output, cost = execute_bash(
            self.mock_tokenizer, interaction, max_tokens=100, timeout_s=0.1
        )

        # Verify partial + final
        self.assertEqual(
            mock_shell.expect.call_count,
            2,
            f"Call count: {mock_shell.expect.call_count}",
        )
        self.assertIn("some final output", output)
        mock_bash_state.set_pending.assert_called()
        mock_bash_state.set_repl.assert_called()
        self.assertEqual(cost, 0)

        #
        # SCENARIO 2: Extended timeouts with more calls
        #
        def mock_expect_extended(patterns, timeout=0.1):
            # We'll keep a list of states
            states = getattr(
                mock_expect_extended,
                "states",
                [
                    ("initial output\n", 1),  # 1 => match TIMEOUT pattern
                    ("command output\n", 0),  # 0 => match prompt
                    ("process exited\n", 0),  # final call => match prompt
                ],
            )
            if not states:
                return 0
            text, ret_index = states.pop(0)
            if ret_index == 1:
                # "simulate" partial
                mock_bash_state.set_pending(text)
            else:
                # matched prompt
                mock_bash_state.set_repl()
            mock_shell.before += text
            return ret_index

        mock_expect_extended.states = [
            ("initial output\n", 1),
            ("command output\n", 0),
        ]

        mock_shell.reset_mock()
        mock_bash_state.reset_mock()
        mock_shell.expect = MagicMock(side_effect=mock_expect_extended)

        interaction = BashCommand(command="test2")
        output, cost = execute_bash(
            self.mock_tokenizer, interaction, max_tokens=100, timeout_s=2
        )
        # Check entire output
        self.assertIn("initial output", output)
        mock_shell.send.assert_any_call("test2")
        mock_bash_state.set_pending.assert_any_call("initial output\n")

        output, cost = execute_bash(
            self.mock_tokenizer,
            BashInteraction(send_specials=["Enter"]),
            max_tokens=100,
            timeout_s=2,
        )
        self.assertIn("command output", output)

        self.assertEqual(mock_shell.expect.call_count, 2)
        mock_bash_state.set_repl.assert_any_call()
        self.assertEqual(mock_bash_state.state, "repl")
        self.assertEqual(cost, 0)

    @patch("wcgw.client.tools.BASH_STATE")
    def test_update_repl_prompt(self, mock_bash_state):
        mock_shell = MagicMock()
        mock_shell.expect.return_value = 1
        mock_shell.before = "new_prompt"
        mock_bash_state.shell = mock_shell

        # Test successful update
        result = update_repl_prompt("wcgw_update_prompt()")
        self.assertTrue(result)

        # Test prompt update with timeouts
        mock_shell.expect.side_effect = [0, 1]  # first is success, second is timeout
        result = update_repl_prompt("wcgw_update_prompt()")
        self.assertTrue(result)

        # Test non-update command
        result = update_repl_prompt("echo test")
        self.assertFalse(result)

    @patch("wcgw.client.tools.BASH_STATE")
    @patch("wcgw.client.tools._ensure_env_and_bg_jobs")
    def test_get_status(self, mock_ensure_env, mock_bash_state):
        # Set up mock shell state
        mock_shell = MagicMock()
        mock_shell.expect.return_value = 0
        mock_shell.before = "/test/cwd"
        mock_bash_state.shell = mock_shell
        mock_bash_state.cwd = "/test/cwd"
        mock_bash_state.update_cwd.return_value = "/test/cwd"
        mock_bash_state.get_pending_for.return_value = "5 seconds"
        mock_bash_state._state = "repl"
        mock_bash_state.state = "repl"

        # Mock _ensure_env_and_bg_jobs => returns int
        mock_ensure_env.return_value = 2

        # pending => "still running"
        mock_bash_state._state = datetime.datetime.now()
        mock_bash_state.state = "pending"
        status = get_status()
        self.assertIn("still running", status)

        # repl => background jobs running
        mock_bash_state._state = "repl"
        mock_bash_state.state = "repl"
        status = get_status()
        self.assertIn("background jobs running", status)

        # no running jobs
        mock_ensure_env.return_value = 0
        status = get_status()
        self.assertIn("process exited", status)
        self.assertNotIn("background jobs running", status)

    def test_render_terminal_output(self):
        # basic
        output = tools.render_terminal_output("Hello\nWorld")
        self.assertEqual([line.rstrip() for line in output], ["Hello", "World"])

        # ANSI
        output = render_terminal_output("\x1b[32mGreen\x1b[0m\nText")
        self.assertEqual([line.rstrip() for line in output], ["Green", "Text"])

        # CRs
        output = render_terminal_output("First\rSecond\nThird")
        self.assertEqual(output[0].rstrip(), "Second")
        self.assertEqual(output[1].rstrip(), "Third")

        # empty lines
        output = render_terminal_output("\n\nHello\n\nWorld\n")
        self.assertEqual(
            [line.rstrip() for line in output], ["", "", "Hello", "", "World"]
        )

        # trailing whitespace
        output = render_terminal_output("Space   \nTabs\t\t\n")
        self.assertEqual([line.rstrip() for line in output], ["Space", "Tabs"])

        # multi lines
        output = render_terminal_output("Left    \nCenter  \nRight")
        self.assertEqual(
            [line.rstrip() for line in output], ["Left", "Center", "Right"]
        )
