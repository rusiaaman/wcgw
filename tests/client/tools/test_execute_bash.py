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
        
        # Setup BASH_STATE
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.pending_output = ""
        mock_bash_state.update_cwd.return_value = "/test/path"
        
        # Create command and execute
        command = BashCommand(command="echo test")
        output, cost = execute_bash(self.mock_tokenizer, command, max_tokens=100, timeout_s=1)
        
        assert "test output" in output.strip()
    
    @patch('wcgw.client.tools.BASH_STATE')
    def test_execute_bash_interaction(self, mock_bash_state):
        mock_shell = MagicMock()
        test_output = render_terminal_output("test output\n")
        mock_shell.before = test_output[0] if test_output else ""
        mock_shell.linesep = "\n"
        
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.pending_output = ""
        mock_bash_state.update_cwd.return_value = "/test/path"
        
        interaction = BashInteraction(send_text="test input")
        output, cost = execute_bash(self.mock_tokenizer, interaction, max_tokens=100, timeout_s=1)
        
        assert "test output" in output.strip()
    
    @patch('wcgw.client.tools.BASH_STATE')
    def test_execute_bash_pending(self, mock_bash_state):
        """Test execution when a command is already running"""
        mock_bash_state.state = "pending"
        
        command = BashCommand(command="echo test")
        with pytest.raises(ValueError, match="A command is already running"):
            execute_bash(self.mock_tokenizer, command, max_tokens=100, timeout_s=1)
    
    @patch('wcgw.client.tools.BASH_STATE')
    def test_execute_bash_large_output(self, mock_bash_state):
        mock_shell = MagicMock()
        large_output = "large output\n" * 10
        test_output = render_terminal_output(large_output)
        mock_shell.before = test_output[0] if test_output else ""
        mock_shell.linesep = "\n"
        
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.pending_output = ""
        mock_bash_state.update_cwd.return_value = "/test/path"
        
        command = BashCommand(command="long_running_command")
        output, cost = execute_bash(self.mock_tokenizer, command, max_tokens=100, timeout_s=1)
        
        assert "large output" in output.strip()