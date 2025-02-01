import pytest
from wcgw.client.tools import BashState


def test_update_repl_prompt_simple():
    """Test updating REPL prompt with valid and invalid commands"""
    state = BashState(working_dir="", bash_command_mode=None, file_edit_mode=None, 
                     write_if_empty_mode=None, mode=None)
    
    # Test with a valid wcgw_update_prompt command
    result = state.update_repl_prompt("wcgw_update_prompt()")
    assert result is True

    # Test with non-prompt update command
    result = state.update_repl_prompt("echo hello")
    assert result is False

def test_update_repl_prompt_whitespace():
    """Test updating REPL prompt with whitespace variations"""
    state = BashState(working_dir="", bash_command_mode=None, file_edit_mode=None, 
                     write_if_empty_mode=None, mode=None)
    
    # Test with whitespace before/after
    result = state.update_repl_prompt("  wcgw_update_prompt()  ")
    assert result is True
    
    result = state.update_repl_prompt("\twcgw_update_prompt()\n")
    assert result is True

import pexpect

def test_update_repl_prompt_error_handling(monkeypatch):
    """Test error handling in prompt update"""
    state = BashState(working_dir="", bash_command_mode=None, file_edit_mode=None, 
                     write_if_empty_mode=None, mode=None)
    
    # Setup shell mock
    class ShellMock:
        before = ""
        def sendintr(self): pass
        def expect(self, *args, **kwargs): return 1  # Return timeout

    shell_mock = ShellMock()
    state._shell = shell_mock
    
    # Test with empty before value
    with pytest.raises(AssertionError, match="Something went wrong updating repl prompt"):
        state.update_repl_prompt("wcgw_update_prompt()")