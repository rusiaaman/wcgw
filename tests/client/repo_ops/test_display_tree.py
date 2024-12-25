import unittest
import tempfile
from pathlib import Path
import os
import shutil
from wcgw.client.repo_ops.display_tree import DirectoryTree

class TestDirectoryTree(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.root_path = Path(self.test_dir)

        # Create a sample directory structure
        # root/
        #   ├── dir1/
        #   │   ├── file1.txt
        #   │   └── file2.txt
        #   ├── dir2/
        #   │   └── subdir/
        #   │       └── file3.txt
        #   └── file4.txt

        # Create directories
        dir1 = self.root_path / "dir1"
        dir1.mkdir()
        dir2 = self.root_path / "dir2"
        dir2.mkdir()
        subdir = dir2 / "subdir"
        subdir.mkdir()

        # Create files
        (dir1 / "file1.txt").write_text("content1")
        (dir1 / "file2.txt").write_text("content2")
        (subdir / "file3.txt").write_text("content3")
        (self.root_path / "file4.txt").write_text("content4")

        self.tree = DirectoryTree(self.root_path)

    def tearDown(self):
        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)

    def test_initialization(self):
        # Test initialization with valid directory
        self.assertEqual(self.tree.root, self.root_path)
        self.assertEqual(self.tree.max_files, 10)
        self.assertEqual(len(self.tree.expanded_files), 0)
        self.assertEqual(len(self.tree.expanded_dirs), 0)

        # Test initialization with non-existent directory
        with self.assertRaises(ValueError):
            DirectoryTree(Path("/nonexistent/path"))

        # Test initialization with file instead of directory
        file_path = self.root_path / "file4.txt"
        with self.assertRaises(ValueError):
            DirectoryTree(file_path)

    def test_expand(self):
        # Test expanding a valid file
        self.tree.expand("file4.txt")
        self.assertIn(self.root_path / "file4.txt", self.tree.expanded_files)
        self.assertIn(self.root_path, self.tree.expanded_dirs)

        # Test expanding a nested file
        self.tree.expand("dir1/file1.txt")
        self.assertIn(self.root_path / "dir1" / "file1.txt", self.tree.expanded_files)
        self.assertIn(self.root_path / "dir1", self.tree.expanded_dirs)

        # Test expanding a deeply nested file
        self.tree.expand("dir2/subdir/file3.txt")
        self.assertIn(self.root_path / "dir2" / "subdir" / "file3.txt", self.tree.expanded_files)
        self.assertIn(self.root_path / "dir2", self.tree.expanded_dirs)
        self.assertIn(self.root_path / "dir2" / "subdir", self.tree.expanded_dirs)

        # Test expanding non-existent file
        with self.assertRaises(ValueError):
            self.tree.expand("nonexistent.txt")

        # Test expanding a directory (should fail)
        with self.assertRaises(ValueError):
            self.tree.expand("dir1")

        # Test path traversal attempt
        with self.assertRaises(ValueError):
            self.tree.expand("../outside.txt")

    def test_list_directory(self):
        # Test listing root directory
        contents = self.tree._list_directory(self.root_path)
        self.assertEqual(len(contents), 3)  # dir1, dir2, file4.txt
        self.assertTrue(all(isinstance(p, Path) for p in contents))

        # Verify directories come before files
        self.assertTrue(contents[0].is_dir())
        self.assertTrue(contents[1].is_dir())
        self.assertTrue(contents[2].is_file())

        # Test listing subdirectory
        dir1_contents = self.tree._list_directory(self.root_path / "dir1")
        self.assertEqual(len(dir1_contents), 2)  # file1.txt, file2.txt
        self.assertTrue(all(p.is_file() for p in dir1_contents))

    def test_count_hidden_items(self):
        # Test with no expanded items
        hidden_files, hidden_dirs = self.tree._count_hidden_items(self.root_path, [])
        self.assertEqual(hidden_files, 1)  # file4.txt
        self.assertEqual(hidden_dirs, 2)   # dir1, dir2

        # Test with some items shown
        shown_items = [
            self.root_path / "dir1",
            self.root_path / "file4.txt"
        ]
        hidden_files, hidden_dirs = self.tree._count_hidden_items(self.root_path, shown_items)
        self.assertEqual(hidden_files, 0)  # file4.txt is shown
        self.assertEqual(hidden_dirs, 1)   # only dir2 is hidden

    def test_display(self):
        # Test initial display (no expansions)
        initial_display = self.tree.display()
        self.assertIn(str(self.root_path), initial_display)
        self.assertIn("2 directories and 1 file hidden", initial_display)

        # Test display with expanded file
        self.tree.expand("file4.txt")
        expanded_display = self.tree.display()
        self.assertIn("file4.txt", expanded_display)
        self.assertIn("2 directories hidden", expanded_display)

        # Test display with expanded nested file
        self.tree.expand("dir1/file1.txt")
        nested_display = self.tree.display()
        self.assertIn("dir1", nested_display)
        self.assertIn("file1.txt", nested_display)
        self.assertIn("1 file hidden", nested_display)  # file2.txt is hidden

        # Test display with all files in dir1 expanded
        self.tree.expand("dir1/file2.txt")
        full_display = self.tree.display()
        self.assertIn("file2.txt", full_display)
        self.assertNotIn("files hidden", full_display)  # all files in dir1 are shown

        # Test display with deeply nested file
        self.tree.expand("dir2/subdir/file3.txt")
        deep_display = self.tree.display()
        self.assertIn("subdir", deep_display)
        self.assertIn("file3.txt", deep_display)
        
if __name__ == "__main__":
    unittest.main()