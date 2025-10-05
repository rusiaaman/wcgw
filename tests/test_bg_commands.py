"""
Tests for background command execution feature.
"""

import tempfile
from typing import Generator

import pytest

from wcgw.client.bash_state.bash_state import BashState
from wcgw.client.tools import (
    BashCommand,
    Context,
    Initialize,
    default_enc,
    get_tool_output,
)
from wcgw.types_ import (
    Command,
    Console,
    SendSpecials,
    StatusCheck,
)


class TestConsole(Console):
    def __init__(self):
        self.logs = []
        self.prints = []

    def log(self, msg: str) -> None:
        self.logs.append(msg)

    def print(self, msg: str) -> None:
        self.prints.append(msg)


@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """Provides a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def context(temp_dir: str) -> Generator[Context, None, None]:
    """Provides a test context with temporary directory and handles cleanup."""
    console = TestConsole()
    bash_state = BashState(
        console=console,
        working_dir=temp_dir,
        bash_command_mode=None,
        file_edit_mode=None,
        write_if_empty_mode=None,
        mode=None,
        use_screen=True,
    )
    ctx = Context(
        bash_state=bash_state,
        console=console,
    )

    # Initialize once for all tests
    init_args = Initialize(
        type="first_call",
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
        thread_id="",
    )
    get_tool_output(
        ctx, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    yield ctx
    # Cleanup after each test
    try:
        bash_state.sendintr()
        bash_state.cleanup()
    except Exception as e:
        print(f"Error during cleanup: {e}")


def test_bg_command_basic(context: Context, temp_dir: str) -> None:
    """Test basic background command execution."""

    # Start a background command
    cmd = BashCommand(
        action_json=Command(command="sleep 2", is_background=True),
        wait_for_seconds=0.1,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert "bg_command_id" in outputs[0]
    assert "status = still running" in outputs[0]

    # Extract bg_command_id from output
    bg_id = None
    for line in outputs[0].split("\n"):
        if "bg_command_id" in line:
            bg_id = line.split("=")[1].strip()
            break

    assert bg_id is not None
    assert len(context.bash_state.background_shells) == 1


def test_bg_command_status_check(context: Context, temp_dir: str) -> None:
    """Test checking status of background command."""

    # Start a background command
    cmd = BashCommand(
        action_json=Command(command="sleep 1", is_background=True),
        wait_for_seconds=0.1,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Extract bg_command_id
    bg_id = None
    for line in outputs[0].split("\n"):
        if "bg_command_id" in line:
            bg_id = line.split("=")[1].strip()
            break

    assert bg_id is not None

    # Check status of background command
    status_cmd = BashCommand(
        action_json=StatusCheck(status_check=True, bg_command_id=bg_id),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, status_cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert "status = process exited" in outputs[0]


def test_bg_command_invalid_id(context: Context, temp_dir: str) -> None:
    """Test error handling for invalid bg_command_id."""

    # Try to check status with invalid bg_command_id
    status_cmd = BashCommand(
        action_json=StatusCheck(status_check=True, bg_command_id="invalid_id"),
        thread_id=context.bash_state._current_thread_id,
    )

    try:
        outputs, _ = get_tool_output(
            context, status_cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
        )
        assert False, "Expected exception for invalid bg_command_id"
    except Exception as e:
        assert "No shell found running with command id" in str(e)


def test_bg_command_interrupt(context: Context, temp_dir: str) -> None:
    """Test interrupting a background command."""

    # Start a background command
    cmd = BashCommand(
        action_json=Command(command="sleep 5", is_background=True),
        wait_for_seconds=0.1,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Extract bg_command_id
    bg_id = None
    for line in outputs[0].split("\n"):
        if "bg_command_id" in line:
            bg_id = line.split("=")[1].strip()
            break

    assert bg_id is not None

    # Send Ctrl-C to background command
    interrupt_cmd = BashCommand(
        action_json=SendSpecials(send_specials=["Ctrl-c"], bg_command_id=bg_id),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, interrupt_cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert "status = process exited" in outputs[0]


def test_multiple_bg_commands(context: Context, temp_dir: str) -> None:
    """Test running multiple background commands simultaneously."""

    # Start first background command
    cmd1 = BashCommand(
        action_json=Command(command="sleep 2", is_background=True),
        wait_for_seconds=0.1,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs1, _ = get_tool_output(
        context, cmd1, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Start second background command
    cmd2 = BashCommand(
        action_json=Command(command="sleep 2", is_background=True),
        wait_for_seconds=0.1,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs2, _ = get_tool_output(
        context, cmd2, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Verify both commands are running
    assert len(context.bash_state.background_shells) == 2
    assert "bg_command_id" in outputs1[0]
    assert "bg_command_id" in outputs2[0]

    # Extract both bg_command_ids
    bg_ids = []
    for output in [outputs1[0], outputs2[0]]:
        for line in output.split("\n"):
            if "bg_command_id" in line:
                bg_ids.append(line.split("=")[1].strip())
                break

    assert len(bg_ids) == 2
    assert bg_ids[0] != bg_ids[1]
