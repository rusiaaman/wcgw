import unittest
from unittest.mock import patch
from src.wcgw.tools import render_terminal_output, ask_confirmation, Writefile, Confirmation

class TestTools(unittest.TestCase):
    def test_render_terminal_output(self):
        # Simulated terminal output
        terminal_output = '\x1b[1;31mHello\x1b[0m\nThis is a test\n\x1b[2K\rLine to clear\n'
        # Taking into account the behavior of pyte
        expected_result = 'Hello\nThis is a test\nLine to clear'
        result = render_terminal_output(terminal_output)
        # Stripping extra whitespace and ensuring content matches
        self.assertEqual('\n'.join(line.strip() for line in result.splitlines()), expected_result)

    @patch('builtins.input', return_value='y')
    def test_ask_confirmation_yes(self, mock_input):
        prompt = 'Are you sure?'
        result = ask_confirmation(Confirmation(prompt=prompt))
        self.assertEqual(result, 'Yes')

    @patch('builtins.input', return_value='n')
    def test_ask_confirmation_no(self, mock_input):
        prompt = 'Are you sure?'
        result = ask_confirmation(Confirmation(prompt=prompt))
        self.assertEqual(result, 'No')

    def test_writefile_model(self):
        # Test the Writefile Pydantic model
        file = Writefile(file_path='test.txt', file_content='This is a test.')
        self.assertEqual(file.file_path, 'test.txt')
        self.assertEqual(file.file_content, 'This is a test.')

if __name__ == '__main__':
    unittest.main()
