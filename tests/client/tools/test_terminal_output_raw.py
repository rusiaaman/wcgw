"""Tests for raw terminal output processing"""
import unittest
from unittest.mock import patch, MagicMock
from wcgw.client.tools import render_terminal_output

class TestTerminalOutputRaw(unittest.TestCase):
    def test_render_empty_output(self):
        """Test rendering empty terminal output"""
        # Test with empty string
        result = render_terminal_output("")
        self.assertEqual(result, [])
        
        # Test with just whitespace
        result = render_terminal_output("    \n   ")
        self.assertEqual(result, [])

    def test_render_simple_output(self):
        """Test rendering simple terminal output"""
        # Test single line with padding handling
        result = render_terminal_output("hello")
        self.assertEqual(result[0].strip(), "hello")

        # Test multiple lines with padding handling
        result = render_terminal_output("line1\nline2\nline3")
        self.assertEqual([line.strip() for line in result], ["line1", "line2", "line3"])
        
    def test_render_special_chars(self):
        """Test rendering output with special characters"""
        # Test backspace character
        result = render_terminal_output("abc\x08d")
        self.assertEqual(result[0].strip(), "abd")
        
        # Test carriage return
        result = render_terminal_output("abc\rdef")
        self.assertEqual(result[0].strip(), "def")
        
        # Test combination
        result = render_terminal_output("abc\x08d\rghijk")
        self.assertEqual(result[0].strip(), "ghijk")
        
    def test_render_ansi_sequences(self):
        """Test rendering ANSI escape sequences"""
        # Test foreground color
        result = render_terminal_output("\033[31mRed Text\033[0m")
        self.assertEqual(result[0].strip(), "Red Text")
        
        # Test background color
        result = render_terminal_output("\033[42mGreen BG\033[0m")
        self.assertEqual(result[0].strip(), "Green BG")
        
        # Test style (bold)
        result = render_terminal_output("\033[1mBold Text\033[0m")
        self.assertEqual(result[0].strip(), "Bold Text")
        
        # Test multiple sequences
        result = render_terminal_output("\033[31m\033[1mBold Red\033[0m")
        self.assertEqual(result[0].strip(), "Bold Red")