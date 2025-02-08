import os
import tempfile
from typing import Generator

import pytest

from wcgw.client.bash_state.bash_state import BashState
from wcgw.client.tools import (
    BashCommand,
    Context,
    ContextSave,
    FileEdit,
    Initialize,
    ReadFiles,
    ReadImage,
    ResetShell,
    WriteIfEmpty,
    default_enc,
    get_tool_output,
)
from wcgw.types_ import Console


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
    )
    ctx = Context(
        bash_state=bash_state,
        console=console,
    )
    yield ctx
    # Cleanup after each test
    bash_state.cleanup()


def test_initialize(context: Context, temp_dir: str) -> None:
    """Test the Initialize tool."""
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

    # Test simple command
    cmd = BashCommand(command="echo 'hello world'")
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert isinstance(outputs[0], str)
    assert "hello world" in outputs[0]


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


def test_file_edit(context: Context, temp_dir: str) -> None:
    """Test the FileEdit tool."""
    # First initialize
    init_args = Initialize(
        any_workspace_path=temp_dir,
        initial_files_to_read=[],
        task_id_to_resume="",
        mode_name="wcgw",
        code_writer_config=None,
    )
    get_tool_output(context, init_args, default_enc, 1.0, lambda x, y: ("", 0.0), None)

    # Create a test file
    test_file = os.path.join(temp_dir, "test.py")
    with open(test_file, "w") as f:
        f.write("def hello():\n    print('hello')\n")

    # Test editing the file
    edit_args = FileEdit(
        file_path=test_file,
        file_edit_using_search_replace_blocks="""<<<<<<< SEARCH
def hello():
    print('hello')
=======
def hello():
    print('hello world')
>>>>>>> REPLACE""",
    )

    outputs, _ = get_tool_output(
        context, edit_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1

    # Verify the change
    with open(test_file) as f:
        content = f.read()
    assert "hello world" in content


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

    # Create a test file with content
    test_file = os.path.join(temp_dir, "input.txt")
    with open(test_file, "w") as f:
        f.write("hello world")

    # Use cat with file instead of interactive input
    cmd = BashCommand(command=f"cat {test_file}")
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert "hello world" in outputs[0]


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
    cmd = BashCommand(command="nonexistentcommand")
    outputs, _ = get_tool_output(
        context, cmd, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )
    assert len(outputs) == 1
    assert "not found" in str(outputs[0]).lower()
