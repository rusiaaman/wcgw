import os
import tempfile
from typing import Generator

import pytest

from wcgw.client.bash_state.bash_state import BashState
from wcgw.client.file_ops.diff_edit import SearchReplaceMatchError
from wcgw.client.file_ops.search_replace import SearchReplaceSyntaxError
from wcgw.client.tools import (
    Context,
    FileEdit,
    Initialize,
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
        use_screen=False,
    )
    ctx = Context(
        bash_state=bash_state,
        console=console,
    )
    yield ctx
    # Cleanup after each test
    bash_state.cleanup()


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

    # Test indentation match
    edit_args = FileEdit(
        file_path=test_file,
        file_edit_using_search_replace_blocks="""<<<<<<< SEARCH
  def hello():
    print('hello world')     
=======
def hello():
    print('ok')
>>>>>>> REPLACE""",
    )

    outputs, _ = get_tool_output(
        context, edit_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert "Warning: matching without considering indentation" in outputs[0]

    # Verify the change
    with open(test_file) as f:
        content = f.read()
    assert "print('ok')" in content

    # Test no match with partial
    edit_args = FileEdit(
        file_path=test_file,
        file_edit_using_search_replace_blocks="""<<<<<<< SEARCH
  def hello():
    print('no match')  
=======
def hello():
    print('no match replace')
>>>>>>> REPLACE""",
    )

    with pytest.raises(SearchReplaceMatchError) as e:
        outputs, _ = get_tool_output(
            context, edit_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
        )

        assert """def hello():
        print('ok')""" in str(e)

        with open(test_file) as f:
            content = f.read()
        assert "print('ok')" in content

    # Test syntax error
    edit_args = FileEdit(
        file_path=test_file,
        file_edit_using_search_replace_blocks="""<<<<<<< SEARCH

def hello():
    print('ok')
=======
def hello():
    print('ok")
>>>>>>> REPLACE""",
    )

    outputs, _ = get_tool_output(
        context, edit_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    assert len(outputs) == 1
    assert "Tree-sitter reported syntax errors" in outputs[0]

    # Verify the change
    with open(test_file) as f:
        content = f.read()
    assert "print('ok\")" in content

    with pytest.raises(SearchReplaceSyntaxError) as e:
        edit_args = FileEdit(
            file_path=test_file,
            file_edit_using_search_replace_blocks="""<<<<<<< SEARCH
def hello():
    print('ok')
=======
def hello():
    print('ok")
>>>>>>> REPLACE
>>>>>>> REPLACE
""",
        )

        outputs, _ = get_tool_output(
            context, edit_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
        )

    with pytest.raises(SearchReplaceSyntaxError) as e:
        edit_args = FileEdit(
            file_path=test_file,
            file_edit_using_search_replace_blocks="""<<<<<<< SEARCH
def hello():
    print('ok')
=======
def hello():
    print('ok")
""",
        )

        outputs, _ = get_tool_output(
            context, edit_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
        )

    # Test multiple matches
    with open(test_file, "w") as f:
        f.write("""
def hello():
    print('ok')
# Comment
def hello():
    print('ok')
""")

    with pytest.raises(SearchReplaceMatchError) as e:
        edit_args = FileEdit(
            file_path=test_file,
            file_edit_using_search_replace_blocks="""<<<<<<< SEARCH
def hello():
    print('ok')
=======
def hello():
    print('hello world')
>>>>>>> REPLACE
""",
        )

        outputs, _ = get_tool_output(
            context, edit_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
        )

    # Grounding should pass even when duplicate found
    edit_args = FileEdit(
        file_path=test_file,
        file_edit_using_search_replace_blocks="""<<<<<<< SEARCH
# Comment
=======
# New Comment
>>>>>>> REPLACE
<<<"""
        + """<<<< SEARCH
def hello():
    print('ok')
=======
def hello():
    print('hello world')
>>>>>>> REPLACE
""",
    )

    outputs, _ = get_tool_output(
        context, edit_args, default_enc, 1.0, lambda x, y: ("", 0.0), None
    )

    with open(test_file) as f:
        content = f.read()
    assert (
        content
        == """
def hello():
    print('ok')
# New Comment
def hello():
    print('hello world')
"""
    )
