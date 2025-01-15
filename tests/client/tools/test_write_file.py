import pytest
from unittest.mock import patch, mock_open, MagicMock
from pathlib import Path
from wcgw.client.tools import write_file
from wcgw.types_ import WriteIfEmpty

class TestWriteFile:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_path = "/test/file.txt"
        self.test_content = "test content"
        self.write_arg = WriteIfEmpty(file_path=self.test_path, file_content=self.test_content)

    @patch("wcgw.client.tools.Path")
    @patch("wcgw.client.tools.BASH_STATE")
    @patch("os.path.exists")
    @patch("os.path.isabs")
    def test_write_file_success(self, mock_isabs, mock_exists, mock_bash_state, mock_path_cls):
        """Test successful file write"""
        # Setup mocks
        mock_isabs.return_value = True
        mock_exists.return_value = False
        mock_bash_state.is_in_docker = None
        mock_bash_state.whitelist_for_overwrite = set()
        mock_bash_state.write_if_empty_mode = MagicMock()
        mock_bash_state.write_if_empty_mode.allowed_globs = "all"
        
        # Setup Path mocking
        mock_path_instance = MagicMock(spec=Path)
        mock_parent = MagicMock(spec=Path)
        mock_parent.mkdir = MagicMock()
        mock_path_instance.parent = mock_parent
        mock_path_cls.return_value = mock_path_instance
        
        # Mock the Path.open method
        mock_file = mock_open()
        mock_path_instance.open = mock_file

        # Write the file
        result = write_file(self.write_arg, error_on_exist=True, max_tokens=100)

        # Verify directory creation
        mock_parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        
        # Verify file operations
        mock_file.assert_called_once_with('w')
        mock_file().write.assert_called_once_with(self.test_content)
        
        # Verify just 'Success' is returned in the result
        assert "Success" in result

    @patch("wcgw.client.tools.Path") 
    @patch("wcgw.client.tools.BASH_STATE")
    @patch("os.path.exists")
    @patch("os.path.isabs")
    def test_write_file_with_existing_file(self, mock_isabs, mock_exists, mock_bash_state, mock_path_cls):
        """Test with existing file"""
        # Setup mocks
        mock_isabs.return_value = True
        mock_exists.return_value = True
        mock_bash_state.is_in_docker = None
        mock_bash_state.whitelist_for_overwrite = set()
        mock_bash_state.write_if_empty_mode = MagicMock()
        mock_bash_state.write_if_empty_mode.allowed_globs = "all"

        # Setup Path with existing content
        mock_path_instance = MagicMock(spec=Path)
        mock_path_instance.read_text.return_value = "existing content"
        mock_path_cls.return_value = mock_path_instance

        result = write_file(self.write_arg, error_on_exist=True, max_tokens=100)
        
        assert "Error: can't write to existing file" in result
        assert "existing content" in result

    @patch("wcgw.client.tools.BASH_STATE") 
    @patch("os.path.isabs")
    def test_write_file_with_relative_path(self, mock_isabs, mock_bash_state):
        """Test with relative path"""
        mock_isabs.return_value = False
        mock_bash_state.cwd = "/current/dir"
        
        write_arg = WriteIfEmpty(file_path="relative/path.txt", file_content=self.test_content)
        result = write_file(write_arg, error_on_exist=True, max_tokens=100)
        
        assert "Failure: file_path should be absolute path" in result
        assert "/current/dir" in result

    @patch("wcgw.client.tools.Path")
    @patch("wcgw.client.tools.BASH_STATE")
    @patch("os.path.exists")
    @patch("os.path.isabs")
    def test_write_file_with_whitelist(self, mock_isabs, mock_exists, mock_bash_state, mock_path_cls):
        """Test with whitelisted file"""
        # Setup mocks
        mock_isabs.return_value = True
        mock_exists.return_value = True
        mock_bash_state.is_in_docker = None
        mock_bash_state.whitelist_for_overwrite = {self.test_path}
        mock_bash_state.write_if_empty_mode = MagicMock()
        mock_bash_state.write_if_empty_mode.allowed_globs = "all"
        
        # Setup Path mocking
        mock_path_instance = MagicMock(spec=Path)
        mock_parent = MagicMock(spec=Path)
        mock_parent.mkdir = MagicMock()
        mock_path_instance.parent = mock_parent
        mock_path_instance.read_text.return_value = "old content"
        mock_file = mock_open()
        mock_path_instance.open = mock_file
        mock_path_cls.return_value = mock_path_instance

        result = write_file(self.write_arg, error_on_exist=True, max_tokens=100)
        
        mock_parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_file.assert_called_once()
        mock_file().write.assert_called_once_with(self.test_content)
        assert "Success" in result or "file.txt" in result