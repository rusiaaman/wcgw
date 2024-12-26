import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from wcgw.client.repo_ops.repo_context import (
    find_ancestor_with_git,
    get_all_files_max_depth,
    get_repo_context,
    PATH_SCORER
)
from pygit2 import GitError


@pytest.fixture
def mock_repo():
    repo = Mock()
    repo.path = "/path/to/repo/.git"
    repo.path_is_ignored = Mock(return_value=False)
    return repo


@pytest.fixture
def mock_directory_tree():
    tree = Mock()
    tree.display = Mock(return_value="Mocked tree display")
    tree.expand = Mock()
    return tree


def test_find_ancestor_with_git_file():
    with patch('wcgw.client.repo_ops.repo_context.Repository') as mock_repo_class:
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        
        result = find_ancestor_with_git(Path("/path/to/file.txt"))
        assert result == mock_repo
        mock_repo_class.assert_called_once_with("/path/to/file.txt")


def test_find_ancestor_with_git_directory():
    with patch('wcgw.client.repo_ops.repo_context.Repository') as mock_repo_class:
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        
        result = find_ancestor_with_git(Path("/path/to/directory"))
        assert result == mock_repo
        mock_repo_class.assert_called_once_with("/path/to/directory")


def test_find_ancestor_with_git_no_git():
    with patch('wcgw.client.repo_ops.repo_context.Repository') as mock_repo_class:
        mock_repo_class.side_effect = GitError
        
        result = find_ancestor_with_git(Path("/path/to/directory"))
        assert result is None


def test_get_all_files_max_depth(tmp_path, mock_repo):
    # Create a test directory structure
    file1 = tmp_path / "file1.txt"
    file1.touch()

    subdir = tmp_path / "subdir"
    subdir.mkdir()
    file2 = subdir / "file2.txt"
    file2.touch()

    # Test with max_depth=0 (should get files only at current level)
    files = get_all_files_max_depth(str(tmp_path), 0, mock_repo)
    assert len(files) == 1  # Only file1.txt at current level
    assert "file1.txt" in files

    # Test with max_depth=1 (should get both files)
    files = get_all_files_max_depth(str(tmp_path), 1, mock_repo)
    assert len(files) == 2
    assert "file1.txt" in files
    assert str(Path("subdir/file2.txt")) in files


def test_get_all_files_max_depth_with_ignored(tmp_path, mock_repo):
    # Setup mock to ignore certain files
    mock_repo.path_is_ignored = Mock(side_effect=lambda x: x == "ignored.txt")
    
    # Create test files
    (tmp_path / "regular.txt").touch()
    (tmp_path / "ignored.txt").touch()
    
    files = get_all_files_max_depth(str(tmp_path), 1, mock_repo)
    assert len(files) == 1
    assert "regular.txt" in files
    assert "ignored.txt" not in files


@patch('wcgw.client.repo_ops.repo_context.DirectoryTree')
def test_get_repo_context_with_git(mock_directory_tree_class, mock_repo, mock_directory_tree):
    mock_directory_tree_class.return_value = mock_directory_tree
    
    with patch('wcgw.client.repo_ops.repo_context.find_ancestor_with_git') as mock_find_git:
        mock_find_git.return_value = mock_repo
        
        with patch('wcgw.client.repo_ops.repo_context.get_all_files_max_depth') as mock_get_files:
            mock_get_files.return_value = ["file1.txt", "file2.txt"]
            
            # Mock PATH_SCORER
            with patch.object(PATH_SCORER, 'calculate_path_probability') as mock_calc:
                mock_calc.side_effect = lambda x: (-1, [], [])
                
                tree_output, context_dir = get_repo_context("/path/to/repo", 10)
                
                assert tree_output == "Mocked tree display"
                assert context_dir == Path("/path/to/repo")
                
                # Verify DirectoryTree was created and used correctly
                mock_directory_tree.expand.assert_any_call("file1.txt")
                mock_directory_tree.expand.assert_any_call("file2.txt")


@patch('wcgw.client.repo_ops.repo_context.DirectoryTree')
def test_get_repo_context_no_git(mock_directory_tree_class, mock_directory_tree):
    mock_directory_tree_class.return_value = mock_directory_tree
    
    with patch('wcgw.client.repo_ops.repo_context.find_ancestor_with_git') as mock_find_git:
        mock_find_git.return_value = None
        
        with patch('wcgw.client.repo_ops.repo_context.get_all_files_max_depth') as mock_get_files:
            mock_get_files.return_value = ["file1.txt", "file2.txt"]
            
            tree_output, context_dir = get_repo_context("/path/to/directory", 10)
            
            assert tree_output == "Mocked tree display"
            assert context_dir == Path("/path/to/directory")


def test_get_repo_context_with_file():
    with patch('wcgw.client.repo_ops.repo_context.find_ancestor_with_git') as mock_find_git:
        mock_find_git.return_value = None
        
        with patch('wcgw.client.repo_ops.repo_context.get_all_files_max_depth') as mock_get_files:
            mock_get_files.return_value = ["file1.txt"]
            
            with patch('wcgw.client.repo_ops.repo_context.DirectoryTree') as mock_tree_class:
                mock_tree = Mock()
                mock_tree.display.return_value = "Tree display"
                mock_tree_class.return_value = mock_tree
                
                with patch('pathlib.Path.is_file') as mock_is_file:
                    mock_is_file.return_value = True
                    tree_output, context_dir = get_repo_context("/path/to/file.txt", 10)
                    
                    assert tree_output == "Tree display"
                    assert context_dir == Path("/path/to")