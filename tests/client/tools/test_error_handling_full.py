"""Tests for error handling in tools.py"""
import unittest
from unittest.mock import patch, MagicMock
from wcgw.client.tools import get_context_for_errors, execute_bash
from wcgw.types_ import BashCommand, BashInteraction

class TestErrorHandling(unittest.TestCase):
    def test_get_context_for_errors(self):
        """Test getting context for error lines"""
        # Test basic error context
        file_content = "line1\nline2\nline3\nline4\nline5"
        errors = [(2, 0)]  # Error on line 2
        
        context = get_context_for_errors(errors, file_content, None)
        self.assertIn("line2", context)  # Error line should be in context
        self.assertIn("line1", context)  # Previous line should be included
        self.assertIn("line3", context)  # Next line should be included
        
        # Test with token limit
        short_context = get_context_for_errors(errors, file_content, 10)
        self.assertEqual(short_context, "Please re-read the file to understand the context")
        
    def test_execute_bash_errors(self):
        """Test error handling during bash execution"""
        mock_tokenizer = MagicMock()
        
        # Test invalid command mode
        with patch('wcgw.client.tools.BASH_STATE') as mock_state:
            mock_state.bash_command_mode.allowed_commands = "none"
            mock_state.update_repl_prompt.return_value = False
            cmd = BashCommand(command="test")
            output, _ = execute_bash(mock_tokenizer, cmd, None, None)
            self.assertIn("Error: BashCommand not allowed", output)
            
        # Test pending state
        with patch('wcgw.client.tools.BASH_STATE') as mock_state:
            mock_state.bash_command_mode.allowed_commands = "all"
            mock_state.state = "pending"
            mock_state.update_repl_prompt.return_value = False
            cmd = BashCommand(command="test")
            with self.assertRaises(ValueError) as cm:
                execute_bash(mock_tokenizer, cmd, None, None)
            self.assertIn("command is already running", str(cm.exception))
            
    def test_bash_interaction_errors(self):
        """Test error handling for bash interaction"""
        mock_tokenizer = MagicMock()
        
        # Test invalid multiple parameters
        interaction = BashInteraction(
            send_text="test",
            send_specials=["Enter"],
            send_ascii=None
        )
        output, _ = execute_bash(mock_tokenizer, interaction, None, None)
        self.assertIn("Failure: exactly one of send_text, send_specials or send_ascii should be provided", output)
        
        # Test command-in-pending error
        with patch('wcgw.client.tools.BASH_STATE') as mock_state:
            mock_state.state = "pending"
            mock_state.bash_command_mode.allowed_commands = "all"
            mock_state.update_repl_prompt.return_value = False
            mock_state.shell = MagicMock()
            
            command = BashCommand(command="test")
            with self.assertRaises(ValueError) as cm:
                execute_bash(mock_tokenizer, command, None, None)
            self.assertIn("A command is already running", str(cm.exception))
            self.assertIn("NOTE:", str(cm.exception))
            
    def test_command_validation(self):
        """Test validation of command inputs"""
        mock_tokenizer = MagicMock()
        
        # Test newline in command
        with patch('wcgw.client.tools.BASH_STATE') as mock_state:
            mock_state.state = "repl"
            mock_state.bash_command_mode.allowed_commands = "all"
            mock_state.update_repl_prompt.return_value = False
            mock_state.shell = MagicMock()
            
            command = BashCommand(command="test\nmore")
            with self.assertRaises(ValueError) as cm:
                execute_bash(mock_tokenizer, command, None, None)
            self.assertIn("should not contain newline", str(cm.exception))
            
    def test_special_char_handling(self):
        """Test handling of special characters in BashInteraction"""
        mock_tokenizer = MagicMock()
        
        # Test multiple parameters provided
        with patch('wcgw.client.tools.BASH_STATE') as mock_state:
            mock_state.state = "repl"
            mock_state.shell = MagicMock()
            interaction = BashInteraction(
                send_text="test",
                send_specials=["Enter"]
            )
            output, _ = execute_bash(mock_tokenizer, interaction, None, None)
            self.assertIn("Failure: exactly one of send_text, send_specials or send_ascii should be provided", output)
            
        # Test valid specials
        with patch('wcgw.client.tools.BASH_STATE') as mock_state:
            # Setup complete mock for shell interaction
            mock_shell = MagicMock()
            mock_shell.before = ""
            mock_shell.expect.return_value = 0
            mock_state.state = "repl"
            mock_state.shell = mock_shell
            mock_state.update_repl_prompt.return_value = False
            mock_state.ensure_env_and_bg_jobs.return_value = 0
            mock_state.cwd = "/test/dir"
            mock_state.update_cwd.return_value = "/test/dir"
            
            # Test valid special key
            interaction = BashInteraction(send_specials=["Enter"])
            output, _ = execute_bash(mock_tokenizer, interaction, None, None)
            
            # Verify shell interactions
            mock_state.shell.send.assert_called_with("\n")
            self.assertIn("status = process exited", output)
            self.assertIn("cwd = /test/dir", output)
            
            # Verify state updates
            mock_state.ensure_env_and_bg_jobs.assert_called_once()
            mock_state.update_cwd.assert_called_once()
            
    def test_keyboard_interrupt(self):
        """Test handling of keyboard interrupts"""
        mock_tokenizer = MagicMock()
        
        with patch('wcgw.client.tools.BASH_STATE') as mock_state:
            # Setup mock state
            mock_shell = MagicMock()
            mock_state.shell = mock_shell
            mock_state.prompt = "TEST>"
            mock_state.state = "repl"
            mock_state.bash_command_mode.allowed_commands = "all"
            mock_state.update_repl_prompt.return_value = False
            
            # Simulate KeyboardInterrupt during execution
            def raise_interrupt(*args, **kwargs):
                raise KeyboardInterrupt()
            mock_shell.send.side_effect = raise_interrupt
            
            command = BashCommand(command="test")
            output, _ = execute_bash(mock_tokenizer, command, None, None)
            
            # Verify interrupt handling
            mock_shell.sendintr.assert_called_once()
            mock_shell.expect.assert_called_with("TEST>")
            self.assertIn("Failure: user interrupted", output)