import datetime
import pytest
from wcgw.client.tools import BashState

def test_get_pending_for_pending():
    """Test get_pending_for when there's a pending operation"""
    state = BashState(working_dir="", bash_command_mode=None, file_edit_mode=None, 
                     write_if_empty_mode=None, mode=None)
    
    # Set a state from 10 seconds ago
    past_time = datetime.datetime.now() - datetime.timedelta(seconds=10)
    state._state = past_time
    
    # The result should be approximately TIMEOUT + 10 seconds
    result = state.get_pending_for()
    
    # Extract the number from "XX seconds"
    seconds = int(result.split()[0])
    
    # Should be around 10 + TIMEOUT (allowing some execution time variance)
    assert 10 <= seconds <= 20  # TIMEOUT is 5 seconds

def test_get_pending_for_not_pending():
    """Test get_pending_for when there's no pending operation"""
    state = BashState(working_dir="", bash_command_mode=None, file_edit_mode=None, 
                     write_if_empty_mode=None, mode=None)
    state._state = "repl"
    
    result = state.get_pending_for()
    assert result == "Not pending"