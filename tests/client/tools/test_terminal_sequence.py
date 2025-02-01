import pytest
from wcgw.client.tools import BashState, render_terminal_output

class TestShellOutput:
    """Test suite for shell output sequence handling"""
    
    def test_output_sequence_with_value(self, monkeypatch):
        """Test terminal output that eventually produces a valid number"""
        state = BashState(working_dir="", bash_command_mode=None, file_edit_mode=None, 
                         write_if_empty_mode=None, mode=None)
        
        # Mock render_terminal_output to simulate terminal output
        def mock_render_terminal_output(text: str) -> list[str]:
            # Extract just the actual command output ignoring setup commands
            if text.endswith("wc -l"):
                return ["jobs"]
            if text == "text1":
                return [""]
            if text == "text2":
                return ["42"]
            return [""]  # Default for setup commands
            
        monkeypatch.setattr('wcgw.client.tools.render_terminal_output', mock_render_terminal_output)
        
        # Setup shell mock with progressive outputs
        class ShellMock:
            def __init__(self):
                self.outputs = [""] * 5  # Setup command outputs
                self.outputs.extend([
                    "text1",  # First call returns empty line
                    "text2",  # Second call returns the number
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
        
        # Test should return the final integer
        assert state.ensure_env_and_bg_jobs() == 42