import unittest
from unittest.mock import patch, MagicMock, mock_open
from wcgw.client.tools import (
    find_least_edit_distance_substring,
    edit_content,
    do_diff_edit,
    get_tool_output,
    which_tool,
    which_tool_name,
    read_files,
    read_file,
    render_terminal_output,
)
from wcgw.types_ import (
    BashCommand,
    FileEdit,
    WriteIfEmpty,
    ReadFiles,
)
import tokenizers


class TestToolsBasic(unittest.TestCase):
    def setUp(self):
        self.test_encoder = tokenizers.Tokenizer.from_pretrained("Xenova/claude-tokenizer")
        
    def test_find_least_edit_distance_substring(self):
        content = [
            "def hello():",
            "    print('hello')",
            "",
            "def world():",
            "    print('world')",
        ]
        search = [
            "def hello():",
            "    print('hello')",
        ]
        
        matched_lines, context = find_least_edit_distance_substring(content, search)
        self.assertEqual(matched_lines, search)
        self.assertTrue(context.startswith("def hello():"))

    def test_edit_content(self):
        content = "def hello():\n    print('hello')\n\ndef world():\n    print('world')"
        find = "def hello():\n    print('hello')"
        replace = "def hello():\n    print('Hello World')"
        
        result = edit_content(content, find, replace)
        self.assertIn("print('Hello World')", result)
        self.assertIn("def world()", result)

    def test_which_tool(self):
        cmd_args = '{"command": "ls", "wait_for_seconds": null}'
        tool = which_tool(cmd_args)
        self.assertIsInstance(tool, BashCommand)

