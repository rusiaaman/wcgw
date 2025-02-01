import pytest
from unittest.mock import MagicMock, patch
from wcgw.client.tools import execute_bash, BashCommand, BashInteraction, render_terminal_output

class TestExecuteBash:
    def setup_method(self):
        self.mock_tokenizer = MagicMock()
    
    @patch('wcgw.client.tools.BASH_STATE')
    def test_execute_bash_command(self, mock_bash_state):
        # Setup mock with rendered output
        mock_shell = MagicMock()
        test_output = render_terminal_output("test output\n")
        mock_shell.before = test_output[0] if test_output else ""
        mock_shell.linesep = "\n"
        mock_shell.expect.return_value = 0

        # Setup BASH_STATE
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.pending_output = ""
        mock_bash_state.update_cwd.return_value = "/test/path"
        mock_bash_state.update_repl_prompt.return_value = False
        mock_bash_state.prompt = "TEST_PROMPT>"
        mock_bash_state.bash_command_mode.allowed_commands = "all"
        mock_bash_state.ensure_env_and_bg_jobs.return_value = 0

        def mock_get_status():
            return "\n\nstatus = process exited\ncwd = /test/path"

        with patch("wcgw.client.tools.get_status", side_effect=mock_get_status):
            # Create command and execute
            command = BashCommand(command="echo test")
            output, cost = execute_bash(self.mock_tokenizer, command, max_tokens=100, timeout_s=1)
            
            assert "test output" in output.strip()
    
    @patch('wcgw.client.tools.BASH_STATE')
    def test_execute_bash_interaction(self, mock_bash_state):
        # Setup mock shell
        mock_shell = MagicMock()
        test_output = render_terminal_output("test output\n")
        mock_shell.before = test_output[0] if test_output else ""
        mock_shell.linesep = "\n" 
        mock_shell.expect.return_value = 0

        # Setup BASH_STATE
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.pending_output = ""
        mock_bash_state.update_cwd.return_value = "/test/path"
        mock_bash_state.update_repl_prompt.return_value = False  # Important: Set this to False
        mock_bash_state.prompt = "TEST_PROMPT>"
        mock_bash_state.ensure_env_and_bg_jobs.return_value = 0

        def mock_get_status():
            return "\n\nstatus = process exited\ncwd = /test/path"

        with patch("wcgw.client.tools.get_status", side_effect=mock_get_status):
            # Create and execute interaction
            interaction = BashInteraction(send_text="test input")
            output, cost = execute_bash(self.mock_tokenizer, interaction, max_tokens=100, timeout_s=1)

            assert "test output" in output.strip()
    
    @patch('wcgw.client.tools.BASH_STATE')
    def test_execute_bash_pending(self, mock_bash_state):
        """Test execution when a command is already running"""
        # Setup mock BASH_STATE
        mock_bash_state.state = "pending"
        mock_bash_state.bash_command_mode.allowed_commands = "all"
        mock_bash_state.update_repl_prompt.return_value = False

        # Test command execution while in pending state
        command = BashCommand(command="echo test")
        with pytest.raises(ValueError) as exc_info:
            execute_bash(self.mock_tokenizer, command, max_tokens=100, timeout_s=1)
        assert "command is already running" in str(exc_info.value).lower()
    
    @patch('wcgw.client.tools.BASH_STATE')
    def test_execute_bash_large_output(self, mock_bash_state):
        # Setup mock shell
        mock_shell = MagicMock()
        large_output = "large output\n" * 10
        test_output = render_terminal_output(large_output)
        mock_shell.before = test_output[0] if test_output else ""
        mock_shell.linesep = "\n"
        mock_shell.expect.return_value = 0
        
        # Setup mock BASH_STATE
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.pending_output = ""
        mock_bash_state.update_cwd.return_value = "/test/path"
        mock_bash_state.update_repl_prompt.return_value = False
        mock_bash_state.prompt = "TEST_PROMPT>"
        mock_bash_state.bash_command_mode.allowed_commands = "all"

        # Mock get_status() function
        def mock_get_status():
            return "\n\nstatus = process exited\ncwd = /test/path"
        
        with patch("wcgw.client.tools.get_status", side_effect=mock_get_status):
            # Test command with large output
            command = BashCommand(command="long_running_command")
            output, cost = execute_bash(self.mock_tokenizer, command, max_tokens=100, timeout_s=1)
            
            # Verify output
            assert "large output" in output.strip()
            assert cost == 0