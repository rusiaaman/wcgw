import unittest
from unittest.mock import patch, MagicMock
from wcgw.client.tools import BASH_STATE, execute_bash
from wcgw.types_ import BashCommand

class TestErrorHandling(unittest.TestCase):
    @patch("wcgw.client.tools.BASH_STATE")
    def test_execute_bash_with_error(self, mock_bash_state):
        mock_shell = MagicMock()
        mock_shell.before = "test output\n"
        mock_shell.expect.side_effect = Exception("Error")
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"

        command = BashCommand(command="invalid command")
        with self.assertRaises(Exception):
            execute_bash(MagicMock(), command, max_tokens=100, timeout_s=1)

if __name__ == "__main__":
    unittest.main()