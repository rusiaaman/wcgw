import pytest
import pexpect
from wcgw.client.tools import BashState, render_terminal_output


class TestEnvAndBgJobs:
    """Test suite for ensure_env_and_bg_jobs method"""

    def test_timeout(self, monkeypatch):
        """Test timeout handling in ensure_env_and_bg_jobs"""
        state = BashState(working_dir="", bash_command_mode=None, file_edit_mode=None, 
                         write_if_empty_mode=None, mode=None)
        
        # Setup shell mock that raises timeout
        class ShellMock:
            before = None
            def expect(self, *args, **kwargs): 
                raise pexpect.TIMEOUT("Mock timeout")
            def sendline(self, cmd: str): pass
                
        shell_mock = ShellMock()
        state._shell = shell_mock
        
        # Should raise when timeout occurs
        with pytest.raises(pexpect.TIMEOUT):
            state.ensure_env_and_bg_jobs()

    def test_shell_output_sequence(self, monkeypatch):
        """Test shell output processing sequence"""
        state = BashState(working_dir="", bash_command_mode=None, file_edit_mode=None, 
                         write_if_empty_mode=None, mode=None)
        
        # Mock render_terminal_output to return input as a single line
        def mock_render_terminal_output(text: str) -> list[str]:
            return [text]
        monkeypatch.setattr('wcgw.client.tools.render_terminal_output', mock_render_terminal_output)
        
        # Setup shell mock that returns a sequence of outputs
        class ShellMock:
            def __init__(self):
                self.outputs = ["0"] * 5  # Initial setup commands return empty
                self.outputs.extend([
                    "not a number",     # First actual output is non-integer
                    "0",                # Final output is a valid integer
                ])
                self.current = 0
            
            @property
            def before(self):
                if self.current < len(self.outputs):
                    val = self.outputs[self.current]
                    self.current += 1
                    return val
                return ""
                
            def expect(self, prompt_pattern, timeout=None): return 0
            def sendline(self, cmd: str): pass
            
        shell_mock = ShellMock()
        state._shell = shell_mock
        
        # Test should return the value 0
        assert state.ensure_env_and_bg_jobs() == 0

    def test_shell_output_to_int(self, monkeypatch):
        """Test shell output eventually returning integer"""
        state = BashState(working_dir="", bash_command_mode=None, file_edit_mode=None, 
                         write_if_empty_mode=None, mode=None)
        
        # Mock render_terminal_output to return input as a single line
        def mock_render_terminal_output(text: str) -> list[str]:
            return [text]
        monkeypatch.setattr('wcgw.client.tools.render_terminal_output', mock_render_terminal_output)
        
        # Setup shell mock that returns integer after some text
        class ShellMock:
            def __init__(self):
                self.outputs = [
                    "some text",   # First call returns text
                    "more text",   # Second call returns text
                    "42",          # Third call returns a number (should return this)
                ]
                self.current = 0
            
            @property
            def before(self):
                if self.current < len(self.outputs):
                    val = self.outputs[self.current]
                    self.current += 1
                    return val
                return ""
                
            def expect(self, *args, **kwargs): return 0
            def sendline(self, cmd: str): pass
            
        shell_mock = ShellMock()
        state._shell = shell_mock
        
        # Test should return the integer we provided
        assert state.ensure_env_and_bg_jobs() == 42