"""Tests for KnowledgeTransfer functionality in tools.py"""

import os
import tempfile
import unittest
from unittest.mock import patch

from wcgw.client.tools import get_tool_output
from wcgw.types_ import ContextSave


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
        
        # Setup save_memory mock
        self.memory_patch = patch("wcgw.client.tools.save_memory")
        self.mock_save_memory = self.memory_patch.start()
        self.mock_save_memory.return_value = "/tmp/memory/test_task_1.txt"

    def tearDown(self):
        self.memory_patch.stop()

    def test_knowledge_transfer_basic(self):
        """Test basic knowledge transfer functionality"""
        with patch("wcgw.client.tools.read_files") as mock_read_files:
            mock_read_files.return_value = self.test_files_content

            description = "Test objective. Instructions: Test instructions. Status: Test status. Issues: Test snippets."
            kt_arg = ContextSave(
                id=self.test_id,
                project_root_path="/test",
                description=description,
                relevant_file_globs=self.test_paths
            )

            outputs, cost = get_tool_output(kt_arg, None, 1.0, lambda x, y: ("", 0), None)
            output = outputs[0]

            self.assertTrue(isinstance(output, str))
            self.assertTrue(output.endswith(".txt"))
            
            # Verify save_memory was called correctly
            self.mock_save_memory.assert_called_once()
            call_args = self.mock_save_memory.call_args[0]
            self.assertEqual(call_args[0].id, self.test_id)
            self.assertEqual(call_args[0].project_root_path, "/test") 
            self.assertEqual(call_args[0].description, description)
            self.assertEqual(call_args[0].relevant_file_globs, self.test_paths)

    def test_knowledge_transfer_with_empty_fields(self):
        """Test knowledge transfer with empty fields"""
        with patch("wcgw.client.tools.read_files") as mock_read_files:
            mock_read_files.return_value = self.test_files_content

            kt_arg = ContextSave(
                id=self.test_id,
                project_root_path="/test",
                description="",
                relevant_file_globs=[]
            )

            outputs, cost = get_tool_output(kt_arg, None, 1.0, lambda x, y: ("", 0), None)
            output = outputs[0]

            self.assertTrue(output.endswith(".txt"))
            
            # Verify save_memory was called correctly
            self.mock_save_memory.assert_called_once()
            call_args = self.mock_save_memory.call_args[0]
            self.assertEqual(call_args[0].description, "")
            self.assertEqual(call_args[0].relevant_file_globs, [])

    def test_knowledge_transfer_file_read_failure(self):
        """Test knowledge transfer when file reading fails"""
        with patch("wcgw.client.tools.read_files") as mock_read_files:
            mock_read_files.return_value = "Failed to read files"

            description = "Test fail case"
            kt_arg = ContextSave(
                id=self.test_id,
                project_root_path="/test",
                description=description,
                relevant_file_globs=self.test_paths
            )

            outputs, cost = get_tool_output(kt_arg, None, 1.0, lambda x, y: ("", 0), None)
            output = outputs[0]

            self.assertTrue(output.endswith(".txt"))
            
            # Verify save_memory was called correctly
            call_args = self.mock_save_memory.call_args[0]
            self.assertEqual(call_args[0].id, self.test_id)
            self.assertEqual(call_args[0].description, description)

    def test_knowledge_transfer_with_long_content(self):
        """Test knowledge transfer with long content"""
        with patch("wcgw.client.tools.read_files") as mock_read_files:
            mock_read_files.return_value = self.test_files_content

            long_content = "A" * 10000  # 10KB of content
            description = f"Test with long content: {long_content}"
            kt_arg = ContextSave(
                id=self.test_id,
                project_root_path="/test",
                description=description,
                relevant_file_globs=self.test_paths
            )

            outputs, cost = get_tool_output(kt_arg, None, 1.0, lambda x, y: ("", 0), None)
            output = outputs[0]

            self.assertTrue(output.endswith(".txt"))
            
            # Verify save_memory was called correctly
            call_args = self.mock_save_memory.call_args[0]
            self.assertEqual(call_args[0].id, self.test_id)
            self.assertEqual(call_args[0].description, description)

    def test_knowledge_transfer_with_special_characters(self):
        """Test knowledge transfer with special characters in fields"""
        with patch("wcgw.client.tools.read_files") as mock_read_files:
            mock_read_files.return_value = self.test_files_content

            special_text = 'Test with special chars: \n\t"\'[]{}!'
            description = f"Test with special characters: {special_text}"
            kt_arg = ContextSave(
                id=self.test_id,
                project_root_path="/test",
                description=description,
                relevant_file_globs=self.test_paths
            )

            outputs, cost = get_tool_output(kt_arg, None, 1.0, lambda x, y: ("", 0), None)
            output = outputs[0]

            self.assertTrue(output.endswith(".txt"))
            
            # Verify save_memory was called correctly
            call_args = self.mock_save_memory.call_args[0]
            self.assertEqual(call_args[0].id, self.test_id)
            self.assertEqual(call_args[0].description, description)


if __name__ == "__main__":
    unittest.main()