import os
import subprocess
import tempfile
from typing import Generator

import pytest

from wcgw.client.bash_state.bash_state import BashState
from wcgw.client.tools import (
    BashCommand,
    Context,
    ContextSave,
    Initialize,
    ReadFiles,
    ReadImage,
    default_enc,
    get_tool_output,
    which_tool_name,
)
from wcgw.types_ import (
    Command,
    Console,
    FileWriteOrEdit,
    SendAscii,
    SendSpecials,
    SendText,
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
    yield ctx
    # Cleanup after each test
    try:
        bash_state.sendintr()  # Send Ctrl-C to any running process
        bash_state.reset_shell()  # Reset shell state
        bash_state.cleanup()  # Cleanup final shell
    except Exception as e:
        print(f"Error during cleanup: {e}")


def test_initialize(context: Context, temp_dir: str) -> None:
    """Test the Initialize tool with various configurations."""
    # Test default wcgw mode
    init_args = Initialize(
        type="first_call",
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
        thread_id="",
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert temp_dir in outputs[0]
    assert "System:" in outputs[0]

    # Test architect mode
    init_args = Initialize(
        type="first_call",
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="architect",
        code_writer_config=None,
        thread_id="",
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)

    # Test code_writer mode with specific configuration
    code_writer_config = {
        "allowed_commands": ["ls", "pwd", "cat"],
        "allowed_globs": ["*.py", "*.txt"],
    }
    init_args = Initialize(
        type="first_call",
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="code_writer",
        code_writer_config=code_writer_config,
        thread_id="",
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)

    # Test with initial files to read and task resumption
    test_file = os.path.join(temp_dir, "test.txt")
    with open(test_file, "w") as f:
        f.write("test content")

    # First save context
    save_args = ContextSave(
        id="test_task_123",
        project_root_path=temp_dir,
        description="Test context",
        relevant_file_globs=["*.txt"],
    )
    get_tool_output(
        context, save_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Now try to resume the saved context
    init_args = Initialize(
        type="first_call",
        any_workspace_path=temp_dir,
        initial_files_to_read=[test_file],
        task_id_to_resume="test_task_123",
        mode_name="wcgw",
        code_writer_config=None,
        thread_id="",
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert test_file in outputs[0]  # Should show the file in tree structure
    assert "Following is the retrieved" in outputs[0]  # Verify context was retrieved

    # Test mode override when resuming context
    # First save context in wcgw mode
    new_test_file = os.path.join(temp_dir, "test2.txt")
    with open(new_test_file, "w") as f:
        f.write("test content 2")

    save_args = ContextSave(
        id="test_task_mode_switch",
        project_root_path=temp_dir,
        description="Test context with mode switch",
        relevant_file_globs=["*.txt"],
    )
    get_tool_output(
        context, save_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Now try to resume the saved context but in architect mode
    init_args = Initialize(
        type="first_call",
        any_workspace_path=temp_dir,
        initial_files_to_read=[new_test_file],
        task_id_to_resume="test_task_mode_switch",
        mode_name="architect",  # Different mode than what was used in saving
        code_writer_config=None,
        thread_id="",
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert new_test_file in outputs[0]  # Should show the file in tree structure
    assert "Following is the retrieved" in outputs[0]  # Verify context was retrieved
    assert (
        'running in "architect" mode' in outputs[0].lower()
    )  # Verify mode was overridden to architect

    # Test with empty workspace path
    init_args = Initialize(
        type="first_call",
        any_workspace_path="",
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
        thread_id="",
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)

    # Test with non-existent workspace path
    nonexistent_path = os.path.join(temp_dir, "does_not_exist")
    init_args = Initialize(
        type="first_call",
        any_workspace_path=nonexistent_path,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
        thread_id="",
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert "does_not_exist" in outputs[0]  # Should mention the path in output

    # Test with a file as workspace path
    file_as_workspace = os.path.join(temp_dir, "workspace.txt")
    with open(file_as_workspace, "w") as f:
        f.write("test content")

    init_args = Initialize(
        type="first_call",
        any_workspace_path=file_as_workspace,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
        thread_id="",
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert file_as_workspace in outputs[0]  # Should show the file path


def test_bash_command(context: Context, temp_dir: str) -> None:
    """Test the BashCommand tool."""
    # First initialize
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
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Test when nothing is running
    cmd = BashCommand(
        action_json=StatusCheck(status_check=True),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert "No running command to check status of" in outputs[0]

    # Start a command and check status
    cmd = BashCommand(
        action_json=Command(command="sleep 1"),
        wait_for_seconds=0.1,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "status = still running" in outputs[0]

    # Check status while command is running
    status_check = BashCommand(
        action_json=StatusCheck(status_check=True),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, status_check, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert "status = process exited" in outputs[0]

    # Test simple command
    cmd = BashCommand(
        action_json=Command(command="echo 'hello world'"),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert "hello world" in outputs[0]

    # Test multiline
    cmd = BashCommand(
        action_json=Command(command="echo 'hello \nworld'"),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert "hello\nworld" in outputs[0]

    # Multiple commands should raise exception
    cmd = BashCommand(
        action_json=Command(command="echo 'hello'\necho world'"),
        thread_id=context.bash_state._current_thread_id,
    )
    try:
        outputs, _ = get_tool_output(
            context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
        )
        assert False, "Expected ValueError to be raised"
    except ValueError as e:
        assert "Error: Command contains multiple statements" in str(e)


def test_interaction_commands(context: Context, temp_dir: str) -> None:
    """Test the various interaction command types."""
    # First initialize
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
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Test text interaction
    cmd = BashCommand(
        action_json=SendText(send_text="hello"),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert isinstance(outputs[0], str)

    # Test special keys
    cmd = BashCommand(
        action_json=SendSpecials(send_specials=["Enter"]),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert "status = process exited" in outputs[0]

    #  Send ctrl-c
    cmd = BashCommand(
        action_json=SendAscii(send_ascii=[3]),
        thread_id=context.bash_state._current_thread_id,
    )  # Ctrl-C
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert "status = process exited" in outputs[0]

    # Test interactions with long running command
    cmd = BashCommand(
        action_json=Command(command="sleep 1"),
        wait_for_seconds=0.1,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "status = still running" in outputs[0]

    # Check status with special keys
    cmd = BashCommand(
        action_json=SendSpecials(send_specials=["Enter"]),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "status = process exited" in outputs[0]

    # Test interrupting command
    cmd = BashCommand(
        action_json=Command(command="sleep 1"),
        wait_for_seconds=0.1,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "status = still running" in outputs[0]

    # Send Ctrl-C
    cmd = BashCommand(
        action_json=SendSpecials(send_specials=["Ctrl-c"]),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert "status = process exited" in outputs[0]


def test_write_and_read_file(context: Context, temp_dir: str) -> None:
    """Test WriteIfEmpty and ReadFiles tools."""
    # First initialize
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
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Test writing a file
    test_file = os.path.join(temp_dir, "test.txt")
    write_args = FileWriteOrEdit(
        file_path=test_file,
        percentage_to_change=100,
        text_or_search_replace_blocks="test content\n",
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, write_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert "Success" in outputs[0]

    # Test reading the file back
    read_args = ReadFiles(file_paths=[test_file])
    outputs, _ = get_tool_output(
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert "test content" in outputs[0]

    # Simulate external modification of the file
    with open(test_file, "w") as f:
        f.write("modified content\n")

    # Attempt to write again
    write_args = FileWriteOrEdit(
        file_path=test_file,
        percentage_to_change=100,
        text_or_search_replace_blocks="new content\n",
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, write_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Verify the error message
    assert "Error: the file has changed since last read." in outputs[0]

    test_file2 = os.path.join(temp_dir, "test2.txt")
    with open(test_file2, "w") as f:
        f.write("existing content\n")
    # Test writing to an existing file without reading it first (should warn)
    write_args = FileWriteOrEdit(
        file_path=test_file2,
        percentage_to_change=100,
        text_or_search_replace_blocks="new content\n",
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, write_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert (
        "Error: you need to read existing " in outputs[0]
    )  # Should fail with exception

    # Test writing after reading the file (should succeed with warning)
    read_args = ReadFiles(file_paths=[test_file2])
    outputs, _ = get_tool_output(
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    write_args = FileWriteOrEdit(
        file_path=test_file2,
        percentage_to_change=100,
        text_or_search_replace_blocks="new content after read\n",
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, write_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert "Success" in outputs[0]

    # Verify the new content was written
    read_args = ReadFiles(file_paths=[test_file2])
    outputs, _ = get_tool_output(
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert "new content after read" in outputs[0]


def test_context_save(context: Context, temp_dir: str) -> None:
    """Test the ContextSave tool."""
    # First initialize
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
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Create some test files
    test_file1 = os.path.join(temp_dir, "test1.txt")
    test_file2 = os.path.join(temp_dir, "test2.txt")

    with open(test_file1, "w") as f:
        f.write("test content 1")
    with open(test_file2, "w") as f:
        f.write("test content 2")

    # Test saving context
    save_args = ContextSave(
        id="test_save",
        project_root_path=temp_dir,
        description="Test save",
        relevant_file_globs=["*.txt"],
    )

    outputs, _ = get_tool_output(
        context, save_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert outputs[0].endswith(".txt")  # Context files end with .txt extension


def test_reinitialize(context: Context, temp_dir: str) -> None:
    """Test the tool with various mode changes."""
    # First initialize
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
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Test shell reset without mode change
    reset_args = Initialize(
        type="user_asked_mode_change",
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, reset_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert "Reset successful" in outputs[0]
    assert "mode change" not in outputs[0].lower()

    # Test changing to architect mode
    reset_args = Initialize(
        type="user_asked_mode_change",
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="architect",
        code_writer_config=None,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, reset_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert "Reset successful with mode change to architect" in outputs[0]

    # Test changing to code_writer mode with config
    code_writer_config = {"allowed_commands": [], "allowed_globs": ["*.py"]}
    reset_args = Initialize(
        type="user_asked_mode_change",
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="code_writer",
        code_writer_config=code_writer_config,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, reset_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert "Reset successful with mode change to code_writer" in outputs[0]
    assert context.bash_state._write_if_empty_mode.allowed_globs == [
        temp_dir + "/" + "*.py"
    ]
    assert context.bash_state.file_edit_mode.allowed_globs == [temp_dir + "/" + "*.py"]

    # Verify mode was actually changed by trying a command not in allowed list
    cmd = BashCommand(
        action_json=Command(command="touch test.txt"),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "Error: BashCommand not allowed in current mode" in str(outputs[0])

    # Test changing to code_writer mode with config
    reset_args = Initialize(
        type="user_asked_change_workspace",
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="shouldnot_proceed",
        mode_name="architect",
        code_writer_config=None,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, reset_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert "Warning: task can only be resumed in a new conversation" in outputs[0]
    assert '"architect" mode' in outputs[0]

    # Test do not print prompt again

    # Test changing to code_writer mode with config
    reset_args = Initialize(
        type="user_asked_change_workspace",
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="architect",
        code_writer_config=None,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, reset_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert "architect mode" not in outputs[0]


def _test_init(context: Context, temp_dir: str) -> None:
    """Initialize test environment."""
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
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    # Reset shell to clean state
    context.bash_state.reset_shell()


def test_file_io(context: Context, temp_dir: str) -> None:
    """Test reading from a file with cat."""
    _test_init(context, temp_dir)

    test_file = os.path.join(temp_dir, "input.txt")
    with open(test_file, "w") as f:
        f.write("hello world")

    cmd = BashCommand(
        action_json=Command(command=f"cat {test_file}"),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert "hello world" in outputs[0]
    assert "status = process exited" in outputs[0]


def test_command_interrupt(context: Context, temp_dir: str) -> None:
    """Test Ctrl-C interruption."""
    _test_init(context, temp_dir)

    cmd = BashCommand(
        action_json=Command(command="sleep 5"),
        wait_for_seconds=0.1,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "status = still running" in outputs[0]

    cmd = BashCommand(
        action_json=SendSpecials(send_specials=["Ctrl-c"]),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "status = process exited" in outputs[0]


def test_command_suspend(context: Context, temp_dir: str) -> None:
    """Test Ctrl-Z suspension."""
    _test_init(context, temp_dir)

    cmd = BashCommand(
        action_json=Command(command="sleep 5"),
        wait_for_seconds=0.1,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "status = still running" in outputs[0]


def test_text_input(context: Context, temp_dir: str) -> None:
    """Test sending text to a program."""
    _test_init(context, temp_dir)

    cmd = BashCommand(
        action_json=Command(command="cat"),
        thread_id=context.bash_state._current_thread_id,
    )
    get_tool_output(context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000)

    cmd = BashCommand(
        action_json=SendText(send_text="hello"),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "hello" in str(outputs[0])

    cmd = BashCommand(
        action_json=SendSpecials(send_specials=["Ctrl-d"]),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "status = process exited" in str(outputs[0])


def test_ascii_input(context: Context, temp_dir: str) -> None:
    """Test sending ASCII codes."""
    _test_init(context, temp_dir)

    cmd = BashCommand(
        action_json=Command(command="cat"),
        thread_id=context.bash_state._current_thread_id,
    )
    get_tool_output(context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000)

    cmd = BashCommand(
        action_json=SendAscii(send_ascii=[65, 66, 67]),
        thread_id=context.bash_state._current_thread_id,
    )  # ABC
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "ABC" in str(outputs[0])

    cmd = BashCommand(
        action_json=SendAscii(send_ascii=[3]),
        thread_id=context.bash_state._current_thread_id,
    )  # Ctrl-C
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert "status = process exited" in str(outputs[0])


def test_read_image(context: Context, temp_dir: str) -> None:
    """Test the ReadImage tool."""
    # First initialize
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
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Create a small test image
    test_image = os.path.join(temp_dir, "test.png")
    with open(test_image, "wb") as f:
        # Write a minimal valid PNG file
        f.write(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63640000000600005c0010ef0000000049454e44ae426082"
            )
        )

    # Test reading image
    read_args = ReadImage(file_path=test_image)
    outputs, _ = get_tool_output(
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert hasattr(outputs[0], "media_type")
    assert outputs[0].media_type == "image/png"
    assert hasattr(outputs[0], "data")


def test_which_tool_name() -> None:
    """Test the which_tool_name function."""
    # Test each tool type
    assert which_tool_name("BashCommand") == BashCommand
    assert which_tool_name("FileWriteOrEdit") == FileWriteOrEdit
    assert which_tool_name("ReadImage") == ReadImage
    assert which_tool_name("ReadFiles") == ReadFiles
    assert which_tool_name("Initialize") == Initialize
    assert which_tool_name("ContextSave") == ContextSave

    # Test error case with unknown tool
    with pytest.raises(ValueError) as exc_info:
        which_tool_name("UnknownTool")
    assert "Unknown tool name: UnknownTool" in str(exc_info.value)


def test_git_recent_files(context: Context, temp_dir: str) -> None:
    """Test git repository recent files feature with 100 files in batches of 20."""
    # Initialize a git repository
    os.chdir(temp_dir)
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)

    # Create 100 files in 5 batches of 20 files each
    all_files = []
    for batch in range(20):
        batch_files = []
        # Create 5 files per batch
        for i in range(5):
            file_num = batch * 5 + i + 1
            file_name = f"file{file_num:03d}.txt"
            batch_files.append(file_name)
            with open(os.path.join(temp_dir, file_name), "w") as f:
                f.write(f"Content for {file_name}")
            subprocess.run(["git", "add", file_name], check=True)

        # Commit this batch
        subprocess.run(["git", "commit", "-m", f"Add batch {batch + 1}"], check=True)
        all_files.extend(batch_files)

    recent_files = all_files[-10:]

    # Initialize with the git repository
    init_args = Initialize(
        type="first_call",
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
        thread_id="",
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)

    # Check that the output contains files from the more recent commits
    repo_structure = outputs[0]

    # All 10 recent files should be in structure
    for file in recent_files:
        assert file in repo_structure


def test_write_empty_file_and_read(context: Context, temp_dir: str) -> None:
    """Test writing an empty file and reading it."""
    _test_init(context, temp_dir)

    test_file = os.path.join(temp_dir, "empty.txt")
    write_args = FileWriteOrEdit(
        file_path=test_file,
        percentage_to_change=100,
        text_or_search_replace_blocks="",
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, write_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert "Success" in outputs[0]

    read_args = ReadFiles(file_paths=[test_file])
    outputs, _ = get_tool_output(
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1


def test_error_cases(context: Context, temp_dir: str) -> None:
    """Test various error cases."""
    # First initialize
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
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )

    # Test reading non-existent file
    read_args = ReadFiles(file_paths=[os.path.join(temp_dir, "nonexistent.txt")])
    outputs, _ = get_tool_output(
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert "Error" in outputs[0]

    # Test writing to non-existent directory
    write_args = FileWriteOrEdit(
        file_path=os.path.join(temp_dir, "nonexistent", "test.txt"),
        text_or_search_replace_blocks="test",
        percentage_to_change=100,
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, write_args, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert "Success" in outputs[0]  # Should succeed as it creates directories

    # Test invalid bash command
    cmd = BashCommand(
        action_json=Command(command="nonexistentcommand"),
        thread_id=context.bash_state._current_thread_id,
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), 8000, 4000
    )
    assert len(outputs) == 1
    assert "not found" in str(outputs[0]).lower()
