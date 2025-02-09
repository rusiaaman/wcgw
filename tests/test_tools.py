import os
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
    ResetShell,
    WriteIfEmpty,
    default_enc,
    get_tool_output,
    which_tool_name,
)
from wcgw.types_ import BashInteraction, Console, FileEdit


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
    bash_state.cleanup()


def test_initialize(context: Context, temp_dir: str) -> None:
    """Test the Initialize tool with various configurations."""
    # Test default wcgw mode
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert temp_dir in outputs[0]
    assert "System:" in outputs[0]

    # Test architect mode
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="architect",
        code_writer_config=None,
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)

    # Test code_writer mode with specific configuration
    code_writer_config = {
        "allowed_commands": ["ls", "pwd", "cat"],
        "allowed_globs": ["*.py", "*.txt"],
    }
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="code_writer",
        code_writer_config=code_writer_config,
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
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
    get_tool_output(context, save_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Now try to resume the saved context
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[test_file],
        task_id_to_resume="test_task_123",
        mode_name="wcgw",
        code_writer_config=None,
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
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
    get_tool_output(context, save_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Now try to resume the saved context but in architect mode
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[new_test_file],
        task_id_to_resume="test_task_mode_switch",
        mode_name="architect",  # Different mode than what was used in saving
        code_writer_config=None,
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
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
        any_workspace_path="",
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)

    # Test with non-existent workspace path
    nonexistent_path = os.path.join(temp_dir, "does_not_exist")
    init_args = Initialize(
        any_workspace_path=nonexistent_path,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert "does_not_exist" in outputs[0]  # Should mention the path in output

    # Test with a file as workspace path
    file_as_workspace = os.path.join(temp_dir, "workspace.txt")
    with open(file_as_workspace, "w") as f:
        f.write("test content")

    init_args = Initialize(
        any_workspace_path=file_as_workspace,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )

    outputs, _ = get_tool_output(
        context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert file_as_workspace in outputs[0]  # Should show the file path


def test_bash_command(context: Context, temp_dir: str) -> None:
    """Test the BashCommand tool."""
    # First initialize
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )
    get_tool_output(context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Test when nothing is running
    cmd = BashCommand(command=None, status_check=True)
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "No running command to check status of" in outputs[0]

    # Start a command and check status
    cmd = BashCommand(command="sleep 1", status_check=False, wait_for_seconds=0.1)
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert "status = still running" in outputs[0]
    # Check status while command is running
    status_check = BashCommand(command=None, status_check=True)
    outputs, _ = get_tool_output(
        context, status_check, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "status = process exited" in outputs[0]

    # Test simple command
    cmd = BashCommand(command="echo 'hello world'", status_check=False)
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert "hello world" in outputs[0]

    # Test BashCommand with both command and status_check
    cmd = BashCommand(command="echo 'test'", status_check=True)
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "test" in outputs[0]


def test_status_check_consistency(context: Context, temp_dir: str) -> None:
    """Test consistency between BashCommand and BashInteraction status checks."""
    # First initialize
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )
    get_tool_output(context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Start a long-running command
    cmd = BashCommand(command="sleep 1", status_check=False, wait_for_seconds=0.1)
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert "status = still running" in outputs[0]

    # Check status using BashInteraction
    interact_status = BashInteraction(send_specials=["Enter"])
    interact_outputs, _ = get_tool_output(
        context, interact_status, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert "status = process exited" in interact_outputs[0]


def test_write_and_read_file(context: Context, temp_dir: str) -> None:
    """Test WriteIfEmpty and ReadFiles tools."""
    # First initialize
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )
    get_tool_output(context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Test writing a file
    test_file = os.path.join(temp_dir, "test.txt")
    write_args = WriteIfEmpty(file_path=test_file, file_content="test content\n")
    outputs, _ = get_tool_output(
        context, write_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert "Success" in outputs[0]

    # Test reading the file back
    read_args = ReadFiles(file_paths=[test_file])
    outputs, _ = get_tool_output(
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert "test content" in outputs[0]

    test_file2 = os.path.join(temp_dir, "test2.txt")
    with open(test_file2, "w") as f:
        f.write("existing content\n")
    # Test writing to an existing file without reading it first (should warn)
    write_args = WriteIfEmpty(file_path=test_file2, file_content="new content\n")
    outputs, _ = get_tool_output(
        context, write_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert (
        "Error: can't write to existing file" in outputs[0]
    )  # Should fail with exception

    # Test writing after reading the file (should succeed with warning)
    read_args = ReadFiles(file_paths=[test_file2])
    outputs, _ = get_tool_output(
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    write_args = WriteIfEmpty(
        file_path=test_file2, file_content="new content after read\n"
    )
    outputs, _ = get_tool_output(
        context, write_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "Warning: a file already existed" in outputs[0]
    assert "Success" in outputs[0]

    # Verify the new content was written
    read_args = ReadFiles(file_paths=[test_file2])
    outputs, _ = get_tool_output(
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "new content after read" in outputs[0]


def test_context_save(context: Context, temp_dir: str) -> None:
    """Test the ContextSave tool."""
    # First initialize
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )
    get_tool_output(context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

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
        context, save_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert outputs[0].endswith(".txt")  # Context files end with .txt extension


def test_reset_shell(context: Context, temp_dir: str) -> None:
    """Test the ResetShell tool."""
    # First initialize
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )
    get_tool_output(context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Test shell reset
    reset_args = ResetShell(should_reset=True)
    outputs, _ = get_tool_output(
        context, reset_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert "Reset successful" in outputs[0]


def test_bash_interaction(context: Context, temp_dir: str) -> None:
    """Test the BashInteraction tool."""
    # First initialize
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )
    get_tool_output(context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Test basic command
    test_file = os.path.join(temp_dir, "input.txt")
    with open(test_file, "w") as f:
        f.write("hello world")
    cmd = BashCommand(command=f"cat {test_file}", status_check=False)
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "hello world" in outputs[0]

    # Test long-running command with BashInteraction
    # Start a sleep command in the background that prints numbers
    cmd = BashCommand(
        command="for i in $(seq 1 5); do echo $i; sleep 1; done", status_check=False
    )
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1

    # Check command output by sending Enter
    check_cmd = BashInteraction(send_specials=["Enter"])
    outputs, _ = get_tool_output(
        context, check_cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) >= 1
    assert any(
        str(i) in str(outputs) for i in range(1, 6)
    )  # Should see some numbers from 1-5

    # Test Ctrl-C handling using yes command
    cmd = BashCommand(
        command="yes 'testing' > /dev/null", status_check=False
    )  # Continuous output command
    get_tool_output(context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    interrupt_cmd = BashInteraction(send_specials=["Ctrl-c"])
    outputs, _ = get_tool_output(
        context, interrupt_cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "status = process exited" in str(outputs[0])

    # Test Ctrl-D handling with cat
    cmd = BashCommand(command="cat > /dev/null", status_check=False)  # Wait for EOF
    get_tool_output(context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Give it a moment to start
    check_cmd = BashInteraction(send_specials=["Enter"])
    get_tool_output(context, check_cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    eof_cmd = BashInteraction(send_specials=["Ctrl-d"])
    get_tool_output(context, eof_cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    assert "status = process exited" in str(outputs[0])

    # Test Ctrl-Z handling
    cmd = BashCommand(
        command="sleep 2", status_check=False, wait_for_seconds=0.1
    )  # Long running command
    get_tool_output(context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    suspend_cmd = BashInteraction(send_specials=["Ctrl-z"])
    outputs, _ = get_tool_output(
        context, suspend_cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1

    # Test ASCII sequence sending
    cmd = BashCommand(command="cat", status_check=False)  # Command that reads input
    get_tool_output(context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Send ASCII sequence (Ctrl-C = ASCII 3)
    send_text = BashInteraction(send_text="hello")
    outputs, _ = get_tool_output(
        context, send_text, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "hello" in str(outputs[0])

    # Send ASCII sequence (Ctrl-C = ASCII 3)
    ascii_cmd = BashInteraction(send_ascii=[3])
    outputs, _ = get_tool_output(
        context, ascii_cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "process exited" in str(outputs[0])

    # Test empty send arguments
    outputs, _ = get_tool_output(
        context,
        BashInteraction(),
        default_enc,
        1.0,
        lambda x, y: ("", 0.0),
        None,
    )
    assert len(outputs) == 1
    assert (
        "exactly one of send_text, send_specials or send_ascii should be provided"
        in outputs[0]
    )


def test_read_image(context: Context, temp_dir: str) -> None:
    """Test the ReadImage tool."""
    # First initialize
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )
    get_tool_output(context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

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
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert hasattr(outputs[0], "media_type")
    assert outputs[0].media_type == "image/png"
    assert hasattr(outputs[0], "data")


def test_which_tool_name() -> None:
    """Test the which_tool_name function."""
    # Test each tool type
    assert which_tool_name("BashCommand") == BashCommand
    assert which_tool_name("BashInteraction") == BashInteraction
    assert which_tool_name("ResetShell") == ResetShell
    assert which_tool_name("WriteIfEmpty") == WriteIfEmpty
    assert which_tool_name("FileEdit") == FileEdit
    assert which_tool_name("ReadImage") == ReadImage
    assert which_tool_name("ReadFiles") == ReadFiles
    assert which_tool_name("Initialize") == Initialize
    assert which_tool_name("ContextSave") == ContextSave

    # Test error case with unknown tool
    with pytest.raises(ValueError) as exc_info:
        which_tool_name("UnknownTool")
    assert "Unknown tool name: UnknownTool" in str(exc_info.value)


def test_error_cases(context: Context, temp_dir: str) -> None:
    """Test various error cases."""
    # First initialize
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )
    get_tool_output(context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Test reading non-existent file
    read_args = ReadFiles(file_paths=[os.path.join(temp_dir, "nonexistent.txt")])
    outputs, _ = get_tool_output(
        context, read_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "Error" in outputs[0]

    # Test writing to non-existent directory
    write_args = WriteIfEmpty(
        file_path=os.path.join(temp_dir, "nonexistent", "test.txt"), file_content="test"
    )
    outputs, _ = get_tool_output(
        context, write_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "Success" in outputs[0]  # Should succeed as it creates directories

    # Test invalid bash command
    cmd = BashCommand(command="nonexistentcommand", status_check=False)
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "not found" in str(outputs[0]).lower()
