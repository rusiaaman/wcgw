import unittest

import tokenizers

from wcgw.client.tools import (
    which_tool,
)
from wcgw.types_ import (
    BashCommand,
)


class TestToolsBasic(unittest.TestCase):
    def setUp(self):
        self.test_encoder = tokenizers.Tokenizer.from_pretrained(
            "Xenova/claude-tokenizer"
        )

    def test_which_tool(self):
        cmd_args = '{"command": "ls", "wait_for_seconds": null}'
        tool = which_tool(cmd_args)
        self.assertIsInstance(tool, BashCommand)
