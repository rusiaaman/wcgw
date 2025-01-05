"""Tests for KnowledgeTransfer functionality in tools.py"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from wcgw.client.tools import (
    get_tool_output,
)
from wcgw.types_ import KnowledgeTransfer


class TestKnowledgeTransfer(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test case"""
        self.maxDiff = None
        self.test_id = "test_task_1"
        test_dir = os.path.join(os.path.dirname(__file__), "test_files")
        os.makedirs(test_dir, exist_ok=True)
        self.test_file_1 = os.path.join(test_dir, "test1.py")
        self.test_file_2 = os.path.join(test_dir, "test2.py")
        self.test_paths = [self.test_file_1, self.test_file_2]
        self.test_files_content = "file content"

    def test_knowledge_transfer_basic(self):
        """Test basic knowledge transfer functionality"""
        # Setup mock
        with patch("wcgw.client.tools.read_files") as mock_read_files:
            mock_read_files.return_value = self.test_files_content

            kt_arg = KnowledgeTransfer(
                id=self.test_id,
                project_root_path="/test",
                objective="Test objective",
                all_user_instructions="Test instructions",
                current_status_of_the_task="Test status",
                all_issues_snippets="Test snippets",
                relevant_file_paths=self.test_paths,
                build_and_development_instructions="Test build instructions",
            )

            # Set up temporary directory structure
            with tempfile.TemporaryDirectory() as tmpdir:
                memory_path = os.path.join(tmpdir, ".local", "share", "wcgw", "memory")
                os.makedirs(memory_path, exist_ok=True)

                def mock_expanduser(path):
                    if path.startswith("~"):
                        return os.path.join(tmpdir, path[2:])
                    return path

                with (
                    patch("os.path.expanduser", side_effect=mock_expanduser),
                    patch("os.makedirs"),
                ):
                    # Execute test
                    outputs, cost = get_tool_output(
                        kt_arg, None, 1.0, lambda x, y: ("", 0), None
                    )
                    output = outputs[0]

                    # Verify output is a path to the memory file
                    self.assertTrue(isinstance(output, str))
                    self.assertTrue(output.endswith(".txt"))

                    # Verify memory files were created
                    memory_file = os.path.join(memory_path, f"{self.test_id}.json")
                    memory_file_full = os.path.join(
                        memory_path, f"{self.test_id}.txt"
                    )
                    self.assertTrue(
                        os.path.exists(memory_file), "JSON memory file not created"
                    )
                    self.assertTrue(
                        os.path.exists(memory_file_full),
                        "Full text memory file not created",
                    )

                    # Verify content
                    with open(memory_file, "r") as f:
                        data = json.loads(f.read())
                        self.assertEqual(data["id"], self.test_id)
                        self.assertEqual(data["project_root_path"], "/test")
                        self.assertEqual(data["objective"], "Test objective")
                        self.assertEqual(
                            data["all_user_instructions"], "Test instructions"
                        )
                        self.assertEqual(data["relevant_file_paths"], self.test_paths)

                    with open(memory_file_full, "r") as f:
                        full_content = f.read()
                        self.assertIn("# Goal: Test objective", full_content)
                        self.assertIn("Test instructions", full_content)
                        self.assertIn("Test snippets", full_content)
                        self.assertIn(self.test_files_content, full_content)

    def test_knowledge_transfer_with_empty_fields(self):
        """Test knowledge transfer with empty fields"""
        with patch("wcgw.client.tools.read_files") as mock_read_files:
            mock_read_files.return_value = self.test_files_content

            kt_arg = KnowledgeTransfer(
                id=self.test_id,
                project_root_path="/test",
                objective="",
                all_user_instructions="",
                current_status_of_the_task="",
                all_issues_snippets="",
                relevant_file_paths=[],
                build_and_development_instructions="",
            )

            # Create temp directory structure
            with tempfile.TemporaryDirectory() as tmpdir:
                memory_base = os.path.join(tmpdir, ".local", "share", "wcgw")
                os.makedirs(memory_base, exist_ok=True)
                memory_dir = os.path.join(memory_base, "memory")
                os.makedirs(memory_dir, exist_ok=True)

                with patch(
                    "os.path.expanduser",
                    return_value=os.path.join(tmpdir, ".local/share"),
                ):
                    # Execute test
                    outputs, cost = get_tool_output(
                        kt_arg, None, 1.0, lambda x, y: ("", 0), None
                    )
                    output = outputs[0]

                    # Verify output
                    self.assertTrue(isinstance(output, str))
                    self.assertTrue(output.endswith(".txt"))

                    # Verify memory files were created and have correct content
                    memory_file = os.path.join(memory_dir, f"{self.test_id}.json")
                    memory_file_full = os.path.join(
                        memory_dir, f"{self.test_id}.txt"
                    )
                    self.assertTrue(
                        os.path.exists(memory_file), "JSON memory file not created"
                    )
                    self.assertTrue(
                        os.path.exists(memory_file_full),
                        "Full text memory file not created",
                    )

                    # Verify empty fields were preserved
                    with open(memory_file, "r") as f:
                        data = json.loads(f.read())
                        self.assertEqual(data["objective"], "")
                        self.assertEqual(data["all_user_instructions"], "")
                        self.assertEqual(data["relevant_file_paths"], [])

    def test_knowledge_transfer_file_read_failure(self):
        """Test knowledge transfer when file reading fails"""
        # Setup mock
        with patch("wcgw.client.tools.read_files") as mock_read_files:
            mock_read_files.return_value = "Failed to read files"

            kt_arg = KnowledgeTransfer(
                id=self.test_id,
                project_root_path="/test",
                objective="Test objective",
                all_user_instructions="Test instructions",
                current_status_of_the_task="Test status",
                all_issues_snippets="Test snippets",
                relevant_file_paths=self.test_paths,
                build_and_development_instructions="Test build instructions",
            )

            # Create temp directory structure
            with tempfile.TemporaryDirectory() as tmpdir:
                memory_base = os.path.join(tmpdir, ".local", "share", "wcgw")
                os.makedirs(memory_base, exist_ok=True)
                memory_dir = os.path.join(memory_base, "memory")
                os.makedirs(memory_dir, exist_ok=True)

                with patch(
                    "os.path.expanduser",
                    return_value=os.path.join(tmpdir, ".local/share"),
                ):
                    # Execute test
                    outputs, cost = get_tool_output(
                        kt_arg, None, 1.0, lambda x, y: ("", 0), None
                    )
                    output = outputs[0]

                    # Verify operation still completes and returns file path
                    self.assertTrue(isinstance(output, str))
                    self.assertTrue(output.endswith(".txt"))

                    # Verify files were created
                    memory_file = os.path.join(memory_dir, f"{self.test_id}.json")
                    memory_file_full = os.path.join(
                        memory_dir, f"{self.test_id}.txt"
                    )
                    self.assertTrue(
                        os.path.exists(memory_file), "JSON memory file not created"
                    )
                    self.assertTrue(
                        os.path.exists(memory_file_full),
                        "Full text memory file not created",
                    )

                    # Verify error message is included in full file content
                    with open(memory_file_full, "r") as f:
                        content = f.read()
                        self.assertIn("Failed to read files", content)

    def test_knowledge_transfer_with_special_characters(self):
        """Test knowledge transfer with special characters in fields"""
        with patch("wcgw.client.tools.read_files") as mock_read_files:
            mock_read_files.return_value = self.test_files_content

            special_text = "Test with special chars: \n\t\"'[]{}!"
            kt_arg = KnowledgeTransfer(
                id=self.test_id,
                project_root_path="/test",
                objective=special_text,
                all_user_instructions=special_text,
                current_status_of_the_task=special_text,
                all_issues_snippets=special_text,
                relevant_file_paths=self.test_paths,
                build_and_development_instructions=special_text,
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                memory_base = os.path.join(tmpdir, ".local", "share", "wcgw")
                os.makedirs(memory_base, exist_ok=True)
                memory_dir = os.path.join(memory_base, "memory")
                os.makedirs(memory_dir, exist_ok=True)

                with patch(
                    "os.path.expanduser",
                    return_value=os.path.join(tmpdir, ".local/share"),
                ):
                    outputs, cost = get_tool_output(
                        kt_arg, None, 1.0, lambda x, y: ("", 0), None
                    )
                    output = outputs[0]

                    # Verify output path returned
                    self.assertTrue(output.endswith(".txt"))

                    # Verify content preserved special characters
                    memory_dir = os.path.join(
                        tmpdir, ".local", "share", "wcgw", "memory"
                    )
                    memory_file = os.path.join(memory_dir, f"{self.test_id}.json")
                    memory_file_full = os.path.join(
                        memory_dir, f"{self.test_id}.txt"
                    )
                    self.assertTrue(os.path.exists(memory_file), "JSON memory file not created")
                    self.assertTrue(os.path.exists(memory_file_full), "Full text memory file not created")

                    with open(memory_file, "r") as f:
                        data = json.loads(f.read())
                        self.assertEqual(data["objective"], special_text)
                        self.assertEqual(data["all_user_instructions"], special_text)

    def test_knowledge_transfer_with_long_content(self):
        """Test knowledge transfer with long content"""
        with patch("wcgw.client.tools.read_files") as mock_read_files:
            mock_read_files.return_value = self.test_files_content

            long_content = "A" * 10000  # 10KB of content
            kt_arg = KnowledgeTransfer(
                id=self.test_id,
                project_root_path="/test",
                objective="Test objective",
                all_user_instructions=long_content,
                current_status_of_the_task="Test status",
                all_issues_snippets=long_content,
                relevant_file_paths=self.test_paths,
                build_and_development_instructions="Test build instructions",
            )

            # Create temp directory structure
            with tempfile.TemporaryDirectory() as tmpdir:
                memory_base = os.path.join(tmpdir, ".local", "share", "wcgw")
                os.makedirs(memory_base, exist_ok=True)
                memory_dir = os.path.join(memory_base, "memory")
                os.makedirs(memory_dir, exist_ok=True)

                with patch(
                    "os.path.expanduser",
                    return_value=os.path.join(tmpdir, ".local/share"),
                ):
                    # Execute test
                    outputs, cost = get_tool_output(
                        kt_arg, None, 1.0, lambda x, y: ("", 0), None
                    )
                    output = outputs[0]

                    # Verify output
                    self.assertTrue(isinstance(output, str))
                    self.assertTrue(output.endswith(".txt"))

                    # Verify files were created
                    memory_file = os.path.join(memory_dir, f"{self.test_id}.json")
                    memory_file_full = os.path.join(
                        memory_dir, f"{self.test_id}.txt"
                    )
                    self.assertTrue(
                        os.path.exists(memory_file), "JSON memory file not created"
                    )
                    self.assertTrue(
                        os.path.exists(memory_file_full),
                        "Full text memory file not created",
                    )

                    # Verify long content is preserved
                    with open(memory_file, "r") as f:
                        data = json.loads(f.read())
                        self.assertEqual(data["all_user_instructions"], long_content)
                        self.assertEqual(data["all_issues_snippets"], long_content)


if __name__ == "__main__":
    unittest.main()
