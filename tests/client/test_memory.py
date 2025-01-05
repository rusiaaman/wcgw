import os
import unittest
from unittest.mock import patch, mock_open
from wcgw.client.memory import get_app_dir_xdg, format_memory, save_memory, load_memory
from wcgw.types_ import KnowledgeTransfer


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.test_task = KnowledgeTransfer(
            id="test_task",
            project_root_path="/test/path",
            objective="Test objective",
            all_user_instructions="Test instructions",
            current_status_of_the_task="Test status",
            all_issues_snippets="Test issues",
            build_and_development_instructions="Test build instructions",
            relevant_file_paths=["/test/file1", "/test/file2"]
        )

    def test_get_app_dir_xdg(self):
        # Test with XDG_DATA_HOME set
        with patch.dict('os.environ', {'XDG_DATA_HOME': '/custom/path'}):
            app_dir = get_app_dir_xdg()
            self.assertEqual(app_dir, '/custom/path/wcgw')

        # Test without XDG_DATA_HOME
        with patch.dict('os.environ', clear=True):
            with patch('os.path.expanduser', return_value='/home/user/.local/share'):
                app_dir = get_app_dir_xdg()
                self.assertEqual(app_dir, '/home/user/.local/share/wcgw')

    def test_format_memory(self):
        relevant_files = "file1\nfile2"
        formatted = format_memory(self.test_task, relevant_files)
        
        self.assertIn("# Goal: Test objective", formatted)
        self.assertIn("# Instructions:\nTest instructions", formatted)
        self.assertIn("# Current Status:\nTest status", formatted)
        self.assertIn("# Pending Issues:\nTest issues", formatted)
        self.assertIn("# Build Instructions:\nTest build instructions", formatted)
        self.assertIn("# Relevant Files:\nfile1\nfile2", formatted)

    @patch('os.makedirs')
    def test_save_memory(self, mock_makedirs):
        with patch('builtins.open', mock_open()) as mock_file:
            relevant_files = "file1\nfile2"
            memory_file = save_memory(self.test_task, relevant_files)
            
            # Verify directory creation
            mock_makedirs.assert_called_once()
            
            # Verify file writes
            mock_file.assert_any_call(memory_file, 'w')
            mock_file.assert_any_call(memory_file.replace('.txt', '.json'), 'w')
            
            # Verify content writes
            handles = mock_file.return_value
            handles.write.assert_any_call(self.test_task.model_dump_json())

    def test_save_memory_empty_id(self):
        task_without_id = KnowledgeTransfer(
            id='',  # Explicitly set an empty id
            project_root_path="/test/path",
            objective="Test objective",
            all_user_instructions="Test instructions",
            current_status_of_the_task="Test status",
            all_issues_snippets="Test issues",
            build_and_development_instructions="Test build instructions",
            relevant_file_paths=["/test/file1", "/test/file2"]
        )
        
        with self.assertRaises(Exception) as context:
            save_memory(task_without_id, "relevant_files")
        self.assertEqual(str(context.exception), "Task id can not be empty")

    def test_load_memory(self):
        mock_json = self.test_task.model_dump_json()
        
        with patch('builtins.open', mock_open(read_data=mock_json)):
            loaded_task = load_memory('test_task')
            
            self.assertEqual(loaded_task.id, self.test_task.id)
            self.assertEqual(loaded_task.objective, self.test_task.objective)
            self.assertEqual(loaded_task.all_user_instructions, self.test_task.all_user_instructions)
            self.assertEqual(loaded_task.current_status_of_the_task, self.test_task.current_status_of_the_task)
            self.assertEqual(loaded_task.all_issues_snippets, self.test_task.all_issues_snippets)
            self.assertEqual(loaded_task.build_and_development_instructions, self.test_task.build_and_development_instructions)
            self.assertEqual(loaded_task.relevant_file_paths, self.test_task.relevant_file_paths)
