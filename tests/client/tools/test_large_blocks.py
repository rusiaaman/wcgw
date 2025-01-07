import unittest
from unittest.mock import patch, MagicMock
from wcgw.client.tools import BASH_STATE, execute_bash
from wcgw.types_ import BashCommand

class TestLargeBlocks(unittest.TestCase):
    @patch("wcgw.client.tools.BASH_STATE")
    def test_execute_bash_large_output(self, mock_bash_state):
        mock_shell = MagicMock()
        mock_shell.before = "large output\n" * 1000
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.update_cwd.return_value = "/test/dir"

        command = BashCommand(command="generate_large_output")
        output, cost = execute_bash(MagicMock(), command, max_tokens=100, timeout_s=1)
        self.assertIn("large output", output)
        self.assertEqual(cost, 0)

if __name__ == "__main__":
    unittest.main()