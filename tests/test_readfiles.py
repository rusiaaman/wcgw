import os
import tempfile
from typing import Optional

from wcgw.types_ import ReadFiles


def test_readfiles_line_number_parsing():
    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
        tmp.write("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")
        tmp_path = tmp.name
    
    try:
        # Test with no line numbers
        read_files = ReadFiles(file_paths=[tmp_path])
        assert read_files.file_paths == [tmp_path]
        assert read_files.start_line_nums == [None]
        assert read_files.end_line_nums == [None]
        
        # Test with start line only (e.g., file.py:2)
        read_files = ReadFiles(file_paths=[f"{tmp_path}:2"])
        assert read_files.file_paths == [tmp_path]
        assert read_files.start_line_nums == [2]
        assert read_files.end_line_nums == [None]
        
        # Test with end line only (e.g., file.py:-3)
        read_files = ReadFiles(file_paths=[f"{tmp_path}:-3"])
        assert read_files.file_paths == [tmp_path]
        assert read_files.start_line_nums == [None]
        assert read_files.end_line_nums == [3]
        
        # Test with start and end lines (e.g., file.py:2-4)
        read_files = ReadFiles(file_paths=[f"{tmp_path}:2-4"])
        assert read_files.file_paths == [tmp_path]
        assert read_files.start_line_nums == [2]
        assert read_files.end_line_nums == [4]
        
        # Test with start line and beyond (e.g., file.py:5-)
        read_files = ReadFiles(file_paths=[f"{tmp_path}:5-"])
        assert read_files.file_paths == [tmp_path]
        assert read_files.start_line_nums == [5]
        assert read_files.end_line_nums == [None]
        
        # Test with multiple files
        read_files = ReadFiles(file_paths=[
            tmp_path,
            f"{tmp_path}:2-3",
            f"{tmp_path}:1-"
        ])
        assert read_files.file_paths == [tmp_path, tmp_path, tmp_path]
        assert read_files.start_line_nums == [None, 2, 1]
        assert read_files.end_line_nums == [None, 3, None]
        
        # Test with invalid line numbers
        read_files = ReadFiles(file_paths=[f"{tmp_path}:invalid-line"])
        assert read_files.file_paths == [f"{tmp_path}:invalid-line"]  # Should keep the whole path
        assert read_files.start_line_nums == [None]
        assert read_files.end_line_nums == [None]
        
        # Test with files that legitimately contain colons
        filename_with_colon = f"{tmp_path}:colon_in_name"
        read_files = ReadFiles(file_paths=[filename_with_colon])
        assert read_files.file_paths == [filename_with_colon]  # Should keep the whole path
        assert read_files.start_line_nums == [None]
        assert read_files.end_line_nums == [None]
        
        # Test with URLs that contain colons
        url_path = "/path/to/http://example.com/file.txt"
        read_files = ReadFiles(file_paths=[url_path])
        assert read_files.file_paths == [url_path]  # Should keep the whole path
        assert read_files.start_line_nums == [None]
        assert read_files.end_line_nums == [None]
        
        # Test with URLs that contain colons followed by valid line numbers
        url_path_with_line = "/path/to/http://example.com/file.txt:10-20"
        read_files = ReadFiles(file_paths=[url_path_with_line])
        assert read_files.file_paths == ["/path/to/http://example.com/file.txt"]
        assert read_files.start_line_nums == [10]
        assert read_files.end_line_nums == [20]
        
    finally:
        # Clean up: remove the temporary file
        os.unlink(tmp_path)


if __name__ == "__main__":
    test_readfiles_line_number_parsing()
    print("All tests passed!")
