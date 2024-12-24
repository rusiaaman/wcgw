import unittest
from unittest.mock import patch, MagicMock
from wcgw.client.common import discard_input, CostData
import sys
import termios
import select


class TestCommon(unittest.TestCase):
    def test_cost_data_model(self):
        """Test CostData model initialization and validation"""
        cost_data = CostData(
            cost_per_1m_input_tokens=0.01,
            cost_per_1m_output_tokens=0.02
        )
        self.assertEqual(cost_data.cost_per_1m_input_tokens, 0.01)
        self.assertEqual(cost_data.cost_per_1m_output_tokens, 0.02)

    @patch('sys.stdin')
    @patch('termios.tcgetattr')
    @patch('termios.tcsetattr')
    @patch('tty.setcbreak')
    @patch('select.select')
    def test_discard_input_with_data(
        self,
        mock_select,
        mock_setcbreak,
        mock_tcsetattr,
        mock_tcgetattr,
        mock_stdin
    ):
        # Mock file descriptor
        mock_stdin.fileno.return_value = 0
        
        # Mock terminal settings
        mock_tcgetattr.return_value = 'old_settings'
        
        # Mock select to indicate there is input first, then no input
        mock_select.side_effect = [
            ([mock_stdin], [], []),  # First call - input available
            ([], [], [])  # Second call - no input
        ]
        
        # Mock reading input
        mock_stdin.read.return_value = 'x'
        
        discard_input()
        
        # Verify terminal settings were properly managed
        mock_tcgetattr.assert_called_once_with(0)
        mock_setcbreak.assert_called_once_with(0)
        mock_tcsetattr.assert_called_once_with(0, termios.TCSADRAIN, 'old_settings')
        
        # Verify input was read
        mock_stdin.read.assert_called_with(1)

    @patch('sys.stdin')
    @patch('termios.tcgetattr')
    @patch('termios.tcsetattr')
    @patch('tty.setcbreak')
    @patch('select.select')
    def test_discard_input_no_data(
        self,
        mock_select,
        mock_setcbreak,
        mock_tcsetattr,
        mock_tcgetattr,
        mock_stdin
    ):
        # Mock file descriptor
        mock_stdin.fileno.return_value = 0
        
        # Mock terminal settings
        mock_tcgetattr.return_value = 'old_settings'
        
        # Mock select to indicate no input
        mock_select.return_value = ([], [], [])
        
        discard_input()
        
        # Verify terminal settings were properly managed
        mock_tcgetattr.assert_called_once_with(0)
        mock_setcbreak.assert_called_once_with(0)
        mock_tcsetattr.assert_called_once_with(0, termios.TCSADRAIN, 'old_settings')
        
        # Verify no input was read
        mock_stdin.read.assert_not_called()

    @patch('sys.stdin')
    @patch('termios.tcgetattr')
    @patch('builtins.print')
    def test_discard_input_error_handling(
        self,
        mock_print,
        mock_tcgetattr,
        mock_stdin
    ):
        # Mock termios error
        mock_tcgetattr.side_effect = termios.error("Mock termios error")
        
        discard_input()
        
        # Verify error was handled gracefully
        mock_print.assert_called_once()
        error_message = mock_print.call_args[0][0]
        self.assertTrue("Warning: Unable to discard input" in error_message)
        self.assertTrue("Mock termios error" in error_message)


if __name__ == "__main__":
    unittest.main()
