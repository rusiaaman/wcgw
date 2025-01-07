import unittest
from unittest.mock import patch, MagicMock
from wcgw.client.tools import BASH_STATE, execute_bash
from wcgw.types_ import BashCommand

class TestDockerOperations(unittest.TestCase):
    @patch("wcgw.client.tools.BASH_STATE")
    def test_execute_bash_in_docker(self, mock_bash_state):
        mock_shell = MagicMock()
        mock_shell.before = "test output\n"
        mock_bash_state.shell = mock_shell
        mock_bash_state.state = "repl"
        mock_bash_state.is_in_docker = "test_container"
        mock_bash_state.update_cwd.return_value = "/test/dir"

        command = BashCommand(command="echo test")
        output, cost = execute_bash(MagicMock(), command, max_tokens=100, timeout_s=1)
        self.assertIn("test output", output)
        self.assertEqual(cost, 0)

if __name__ == "__main__":
    unittest.main()