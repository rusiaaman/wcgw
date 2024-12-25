import sys
from unittest import mock
with mock.patch.dict(sys.modules, {'syntax_checker': mock.MagicMock()}):
    import unittest
    import tempfile
    from pathlib import Path
    import shutil
    from wcgw.client.repo_ops.display_tree import DirectoryTree

class TestDirectoryTree(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root_path = Path(self.test_dir)
        (self.root_path / "test.txt").write_text("test")
        (self.root_path / "dir").mkdir()
        (self.root_path / "dir" / "nested.txt").write_text("nested")
        self.tree = DirectoryTree(self.root_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_initialization_and_errors(self):
        # Test invalid paths
        with self.assertRaises(ValueError):
            DirectoryTree(Path("/nonexistent/path"))
        with self.assertRaises(ValueError):
            DirectoryTree(self.root_path / "test.txt")  # file path

    def test_expand_errors(self):
        # Test path validation errors in expand
        with self.assertRaises(ValueError):
            self.tree.expand("nonexistent.txt")
        with self.assertRaises(ValueError):
            self.tree.expand("dir")  # directory path
        with self.assertRaises(ValueError):
            self.tree.expand("../outside.txt")

        # Test empty directory case
        empty_dir = self.root_path / "empty"
        empty_dir.mkdir()
        display = self.tree.display()
        self.assertIn("2 directories and 1 file hidden", display)  # Updated assertion

    def test_expand_and_display(self):
        # Basic display
        display = self.tree.display()
        self.assertIn("1 directory and 1 file hidden", display)

        # Expand and verify
        self.tree.expand("test.txt")
        display = self.tree.display()
        self.assertIn("test.txt", display)
        self.assertIn("1 directory hidden", display)

        # Test nested file
        self.tree.expand("dir/nested.txt")
        display = self.tree.display()
        self.assertIn("nested.txt", display)
        self.assertNotIn("hidden", display)

if __name__ == "__main__":
    unittest.main()