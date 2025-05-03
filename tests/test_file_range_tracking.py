import os
import tempfile
from typing import Dict, List, Tuple

import pytest

from wcgw.client.bash_state.bash_state import BashState, FileWhitelistData
from wcgw.client.tools import Context, read_file, read_files


class MockConsole:
    def print(self, msg: str, *args, **kwargs) -> None:
        pass

    def log(self, msg: str, *args, **kwargs) -> None:
        pass


@pytest.fixture
def test_file():
    """Create a temporary file with 20 lines of content."""
    with tempfile.NamedTemporaryFile(delete=False, mode="w") as f:
        for i in range(1, 21):
            f.write(f"Line {i}\n")
        path = f.name

    yield path

    # Cleanup
    os.unlink(path)


@pytest.fixture
def context():
    """Create a context with BashState for testing."""
    with BashState(
        console=MockConsole(),
        working_dir="",
        bash_command_mode=None,
        file_edit_mode=None,
        write_if_empty_mode=None,
        mode=None,
        use_screen=False,
    ) as bash_state:
        return Context(bash_state=bash_state, console=MockConsole())


def test_read_file_tracks_line_ranges(test_file, context):
    """Test that read_file correctly returns line ranges."""
    # Read lines 5-10
    _, _, _, path, line_range = read_file(
        test_file, coding_max_tokens=None, noncoding_max_tokens=None, context=context, start_line_num=5, end_line_num=10
    )

    # Check that the line range is correct
    assert line_range == (5, 10)


def test_read_files_tracks_multiple_ranges(test_file, context):
    """Test that read_files correctly collects line ranges for multiple reads."""
    # Create a second test file
    with tempfile.NamedTemporaryFile(delete=False, mode="w") as f:
        for i in range(1, 31):
            f.write(f"Another line {i}\n")
        second_file = f.name

    try:
        # Read different ranges from both files
        _, file_ranges, _ = read_files(
            file_paths=[test_file, second_file],
            coding_max_tokens=None,
            noncoding_max_tokens=None,
            context=context,
            start_line_nums=[5, 10],
            end_line_nums=[10, 20],
        )

        # Check that the file ranges dictionary has both files with correct ranges
        assert len(file_ranges) == 2
        assert test_file in file_ranges
        assert second_file in file_ranges
        assert file_ranges[test_file] == [(5, 10)]
        assert file_ranges[second_file] == [(10, 20)]
    finally:
        # Cleanup
        os.unlink(second_file)


def test_whitelist_data_tracking(test_file):
    """Test that FileWhitelistData correctly tracks line ranges."""
    # Create whitelist data with some initial ranges and a total of 20 lines
    whitelist_data = FileWhitelistData(
        file_hash="abc123", line_ranges_read=[(1, 5), (10, 15)], total_lines=20
    )

    # Add another range
    whitelist_data.add_range(7, 9)

    # Calculate percentage
    percentage = whitelist_data.get_percentage_read()

    # We've read lines 1-5, 7-9, and 10-15, so 14 out of 20 lines = 70%
    assert percentage == 70.0

    # Test is_read_enough
    assert not whitelist_data.is_read_enough()

    # Test get_unread_ranges
    unread_ranges = whitelist_data.get_unread_ranges()
    # We've read lines 1-5, 7-9, and 10-15, so we're missing 6 and 16-20
    assert len(unread_ranges) == 2
    assert (6, 6) in unread_ranges
    assert (16, 20) in unread_ranges

    # Add remaining lines
    whitelist_data.add_range(6, 6)
    whitelist_data.add_range(16, 20)

    # Now we should have read everything
    assert whitelist_data.is_read_enough()
    assert len(whitelist_data.get_unread_ranges()) == 0


def test_bash_state_whitelist_for_overwrite(context, test_file):
    """Test that BashState correctly tracks file whitelist data."""
    # Create a dictionary mapping the test file to a line range
    file_paths_with_ranges: Dict[str, List[Tuple[int, int]]] = {test_file: [(1, 10)]}

    # Add to whitelist
    context.bash_state.add_to_whitelist_for_overwrite(file_paths_with_ranges)

    # Check that the file was added to the whitelist
    assert test_file in context.bash_state.whitelist_for_overwrite

    # Check that the line range was stored correctly
    whitelist_data = context.bash_state.whitelist_for_overwrite[test_file]
    assert whitelist_data.line_ranges_read[0] == (1, 10)

    # Add another range
    context.bash_state.add_to_whitelist_for_overwrite({test_file: [(15, 20)]})

    # Check that the new range was added
    whitelist_data = context.bash_state.whitelist_for_overwrite[test_file]
    assert len(whitelist_data.line_ranges_read) == 2
    assert (15, 20) in whitelist_data.line_ranges_read
