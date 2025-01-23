"""Additional tests for terminal output handling in tools.py"""

import unittest
from unittest.mock import patch

from wcgw.client.tools import (
    Confirmation,
    _incremental_text,
    _is_int,
    ask_confirmation,
    get_incremental_output,
    render_terminal_output,
)


class TestTerminalOutputFull(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test case"""
        self.maxDiff = None

    def test_get_incremental_output_break_conditions(self):
        """Test break conditions in get_incremental_output"""
        # Test case 1: No match found - returns entire new output
        old_output = ["old"]
        new_output = ["diff1", "diff2"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, new_output)  # No match, return all

        # Test case 2: Last line matches but not complete sequence - returns entire new output
        old_output = ["start", "last"]
        new_output = [
            "other",
            "last",
            "extra",
        ]  # Matches last line but not full sequence
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, new_output)  # Incomplete match, return all

        # Test case 3: Empty old output - returns entire new output
        old_output = []
        new_output = ["line1", "line2"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, new_output)  # Empty old, return all

        # Test case 4: Complete sequence match - returns only new content after match
        old_output = ["start", "middle"]
        new_output = ["start", "middle", "extra"]  # Complete sequence matches
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, ["extra"])  # Complete match, return only new content

    def test_incremental_terminal_output(self):
        """Test incremental terminal output handling"""
        # Test with completely empty old output
        result = _incremental_text("new text", "")
        self.assertEqual(result.rstrip(), "new text")

        # Test with new output matching end of old
        result = _incremental_text(
            "some existing text\nnew text", "some existing text\n"
        )
        self.assertEqual(result.rstrip(), "new text")

    def test_ask_confirmation(self):
        """Test ask_confirmation function"""
        with patch("builtins.input", return_value="y"):
            result = ask_confirmation(Confirmation(prompt="Test prompt"))
            self.assertEqual(result, "Yes")

        with patch("builtins.input", return_value="n"):
            result = ask_confirmation(Confirmation(prompt="Test prompt"))
            self.assertEqual(result, "No")

        # Test with other input that should be treated as no
        with patch("builtins.input", return_value="anything"):
            result = ask_confirmation(Confirmation(prompt="Test prompt"))
            self.assertEqual(result, "No")

    def test_terminal_empty_output(self):
        """Test render_terminal_output with empty lines and whitespace"""
        # Test with completely empty output
        result = render_terminal_output("")
        self.assertEqual(result, [])

        # Test with non-empty followed by empty lines
        result = render_terminal_output("line1\nline2\n  \n\n")
        result = [line.rstrip() for line in result]  # Strip trailing spaces
        self.assertEqual(result, ["line1", "line2"])  # Empty lines at end are filtered

        # Test with content between empty lines
        result = render_terminal_output("\n\nline1\n\nline2\n")
        result = [line.rstrip() for line in result]
        self.assertEqual(
            result, ["", "", "line1", "", "line2"]
        )  # Empty at start kept, at end filtered

        # Test with trailing whitespace lines
        result = render_terminal_output("line1\n   \n  ")
        result = [line.rstrip() for line in result]
        self.assertEqual(result, ["line1"])  # Whitespace at end filtered

    def test_is_int_function(self):
        """Test _is_int function with various inputs"""
        self.assertTrue(_is_int("123"))  # Valid integer
        self.assertTrue(_is_int("-123"))  # Negative integer
        self.assertTrue(_is_int("0"))  # Zero

        self.assertFalse(_is_int("abc"))  # Letters
        self.assertFalse(_is_int("12.3"))  # Float
        self.assertFalse(_is_int(""))  # Empty string
        self.assertFalse(_is_int(" "))  # Whitespace


if __name__ == "__main__":
    unittest.main()
