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
        type="first_call",
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
    assert "Warning: tree-sitter reported syntax errors" in outputs[0]

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


import re


def fix_indentation(
    matched_lines: list[str], searched_lines: list[str], replaced_lines: list[str]
) -> list[str]:
    if not matched_lines or not searched_lines or not replaced_lines:
        return replaced_lines

    def get_indentation(line: str) -> str:
        match = re.match(r"^(\s*)", line)
        assert match
        return match.group(0)

    matched_indents = [get_indentation(line) for line in matched_lines if line.strip()]
    searched_indents = [
        get_indentation(line) for line in searched_lines if line.strip()
    ]
    if len(matched_indents) != len(searched_indents):
        return replaced_lines

    diffs: list[int] = [
        len(searched) - len(matched)
        for matched, searched in zip(matched_indents, searched_indents)
    ]
    if not diffs:
        return replaced_lines
    if not all(diff == diffs[0] for diff in diffs):
        return replaced_lines

    if diffs[0] == 0:
        return replaced_lines

    def adjust_indentation(line: str, diff: int) -> str:
        if diff < 0:
            # Need to add -diff spaces
            return matched_indents[0][:-diff] + line
        # Need to remove diff spaces
        return line[diff:]

    if diffs[0] > 0:
        # Check if replaced_lines have enough leading spaces to remove
        if not all(not line[: diffs[0]].strip() for line in replaced_lines):
            return replaced_lines

    return [adjust_indentation(line, diffs[0]) for line in replaced_lines]


def test_empty_inputs():
    assert fix_indentation([], ["  foo"], ["    bar"]) == ["    bar"]
    assert fix_indentation(["  foo"], [], ["    bar"]) == ["    bar"]
    assert fix_indentation(["  foo"], ["  foo"], []) == []


def test_no_non_empty_lines_in_matched_or_searched():
    # All lines in matched_lines/searched_lines are blank or just spaces
    matched_lines = ["   ", "  "]
    searched_lines = ["   ", "\t "]
    replaced_lines = ["   Some text", "   Another text"]
    # Because matched_lines / searched_lines effectively have 0 non-empty lines,
    # the function returns replaced_lines as is
    assert (
        fix_indentation(matched_lines, searched_lines, replaced_lines) == replaced_lines
    )


def test_same_indentation_no_change():
    # The non-empty lines have the same indentation => diff=0 => no changes
    matched_lines = ["    foo", "    bar"]
    searched_lines = ["    baz", "    qux"]
    replaced_lines = ["        spam", "        ham"]
    # Should return replaced_lines unchanged
    assert (
        fix_indentation(matched_lines, searched_lines, replaced_lines) == replaced_lines
    )


def test_positive_indentation_difference():
    # matched_lines have fewer spaces than searched_lines => diff > 0 => remove indentation from replaced_lines
    matched_lines = ["  foo", "  bar"]
    searched_lines = ["    foo", "    bar"]
    replaced_lines = ["    spam", "    ham"]
    # diff is 2 => remove 2 spaces from the start of each replaced line
    expected = ["  spam", "  ham"]
    assert fix_indentation(matched_lines, searched_lines, replaced_lines) == expected


def test_positive_indentation_not_enough_spaces():
    # We want to remove 2 spaces, but replaced_lines do not have that many leading spaces
    matched_lines = ["foo", "bar"]
    searched_lines = ["    foo", "    bar"]
    replaced_lines = [" spam", " ham"]  # only 1 leading space
    # The function should detect there's not enough indentation to remove => return replaced_lines unchanged
    assert (
        fix_indentation(matched_lines, searched_lines, replaced_lines) == replaced_lines
    )


def test_negative_indentation_difference():
    # matched_lines have more spaces than searched_lines => diff < 0 => add indentation to replaced_lines
    matched_lines = ["    foo", "    bar"]
    searched_lines = ["  foo", "  bar"]
    replaced_lines = ["spam", "ham"]
    # diff is -2 => add 2 spaces from matched_indents[0] to each line
    # matched_indents[0] = '    ' => matched_indents[0][:-diff] => '    '[:2] => '  '
    expected = ["  spam", "  ham"]
    assert fix_indentation(matched_lines, searched_lines, replaced_lines) == expected


def test_different_number_of_non_empty_lines():
    # matched_indents and searched_indents have different lengths => return replaced_lines
    matched_lines = [
        "    foo",
        "      ",
        "    baz",
    ]  # effectively 2 non-empty lines
    searched_lines = ["  foo", "  bar", "  baz"]  # 3 non-empty lines
    replaced_lines = ["  spam", "  ham"]
    assert (
        fix_indentation(matched_lines, searched_lines, replaced_lines) == replaced_lines
    )


def test_inconsistent_indentation_difference():
    # The diffs are not all the same => return replaced_lines
    matched_lines = ["    foo", "        bar"]
    searched_lines = ["  foo", "    bar"]
    replaced_lines = ["spam", "ham"]
    # For the first pair, diff = len("  ") - len("    ") = 2 - 4 = -2
    # For the second pair, diff = len("    ") - len("        ") = 4 - 8 = -4
    # Not all diffs are equal => should return replaced_lines
    assert (
        fix_indentation(matched_lines, searched_lines, replaced_lines) == replaced_lines
    )


def test_realistic_fix_indentation_scenario():
    matched_lines = [
        "  class Example:",
        "      def method(self):",
        "          print('hello')",
    ]
    searched_lines = [
        "class Example:",
        "    def method(self):",
        "        print('world')",
    ]
    replaced_lines = [
        "class Example:",
        "    def another_method(self):",
        "        print('world')",
    ]
    expected = [
        "  class Example:",
        "      def another_method(self):",
        "          print('world')",
    ]
    assert fix_indentation(matched_lines, searched_lines, replaced_lines) == expected


def test_realistic_nonfix_indentation_scenario():
    matched_lines = [
        "  class Example:",
        "      def method(self):",
        "            print('hello')",
    ]
    searched_lines = [
        "class Example:",
        "    def method(self):",
        "        print('world')",
    ]
    replaced_lines = [
        "class Example:",
        "    def another_method(self):",
        "        print('world')",
    ]
    assert (
        fix_indentation(matched_lines, searched_lines, replaced_lines) == replaced_lines
    )
