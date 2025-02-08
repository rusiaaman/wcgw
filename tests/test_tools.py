import unittest
from unittest.mock import patch

from wcgw.client.bash_state.bash_state import render_terminal_output
from wcgw.types_ import WriteIfEmpty


class TestTools(unittest.TestCase):
    def test_render_terminal_output(self) -> None:
        # Simulated terminal output
        terminal_output = (
            "\x1b[1;31mHello\x1b[0m\nThis is a test\n\x1b[2K\rLine to clear\n"
        )
        # Taking into account the behavior of pyte
        expected_result = "Hello\nThis is a test\nLine to clear"
        result = render_terminal_output(terminal_output)
        # Stripping extra whitespace and ensuring content matches
        self.assertEqual("\n".join(line.strip() for line in result), expected_result)

    def test_writefile_model(self):
        # Test the Writefile Pydantic model
        file = WriteIfEmpty(file_path="test.txt", file_content="This is a test.")
        self.assertEqual(file.file_path, "test.txt")
        self.assertEqual(file.file_content, "This is a test.")


if __name__ == "__main__":
    unittest.main()
