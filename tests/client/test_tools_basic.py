import unittest
from unittest.mock import patch, MagicMock, mock_open
from wcgw.client.tools import (
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
        
    def test_which_tool(self):
        cmd_args = '{"command": "ls", "wait_for_seconds": null}'
        tool = which_tool(cmd_args)
        self.assertIsInstance(tool, BashCommand)

