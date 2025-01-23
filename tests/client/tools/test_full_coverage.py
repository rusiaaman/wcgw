import logging
import unittest
from unittest.mock import MagicMock, patch

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from wcgw.client.tools import (
    get_incremental_output,
    render_terminal_output,
    truncate_if_over,
)


class TestFullCoverage(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_incremental_output_single_case(self):
        """Simple test for get_incremental_output function"""
        old_output = ["line1", "line2"]
        new_output = ["line2", "line3"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, ["line3"])

    def test_render_terminal_basic(self):
        """Test render_terminal_output function"""
        # Test basic output
        result = render_terminal_output("Hello\nWorld")
        self.assertEqual([line.rstrip() for line in result], ["Hello", "World"])

        # Test with ANSI escape codes
        result = render_terminal_output("\x1b[32mColored\x1b[0m\nText")
        self.assertEqual([line.rstrip() for line in result], ["Colored", "Text"])

    def test_truncate_if_over(self):
        """Test truncate_if_over function"""
        # Test with no truncation needed
        with patch("wcgw.client.tools.default_enc") as mock_enc:
            mock_enc.encode.return_value = [1, 2, 3]  # Under limit
            result = truncate_if_over("short content", max_tokens=100)
            self.assertEqual(result, "short content")

        # Test with truncation needed
        with patch("wcgw.client.tools.default_enc") as mock_enc:
            mock_encoding = MagicMock()
            mock_encoding.ids = list(range(200))  # Over limit
            mock_encoding.__len__.return_value = 200
            mock_enc.encode.return_value = mock_encoding
            mock_enc.decode.return_value = "truncated"

            result = truncate_if_over("long content", max_tokens=50)
            self.assertIn("truncated", result)
            self.assertIn("(...truncated)", result)

        # Test with None max_tokens
        result = truncate_if_over("any content", max_tokens=None)
        self.assertEqual(result, "any content")

        # Test with zero max_tokens
        result = truncate_if_over("any content", max_tokens=0)
        self.assertEqual(result, "any content")


if __name__ == "__main__":
    unittest.main()
