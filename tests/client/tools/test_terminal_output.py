"""Tests for terminal output handling in tools.py"""
import unittest
from unittest.mock import patch, MagicMock
import logging
import sys
import pyte

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)
from wcgw.client.tools import (
    render_terminal_output,
    _incremental_text,
    get_incremental_output,
)

def mock_pyte_screen():
    """Create a mock pyte screen"""
    logger.debug("Creating mock pyte screen")
    try:
        screen = pyte.Screen(80, 24)  # Standard terminal size
        screen.set_mode(pyte.modes.LNM)
        logger.debug("Mock screen created successfully")
        return screen
    except Exception as e:
        logger.error(f"Error creating mock screen: {e}")
        raise

def mock_pyte_stream(screen):
    """Create a mock pyte stream"""
    stream = pyte.Stream(screen)
    return stream

class TestTerminalOutput(unittest.TestCase):
    def setUp(self):
        logger.info("Setting up TestTerminalOutput test")
        self.maxDiff = None

    def tearDown(self):
        logger.info("Tearing down TestTerminalOutput test")

    def test_render_terminal_output(self):
        """Test rendering of terminal output with various sequences"""
        logger.info("Starting test_render_terminal_output")
        
        # Create a real pyte screen and stream for rendering
        try:
            logger.debug("Creating screen and stream")
            screen = mock_pyte_screen()
            stream = mock_pyte_stream(screen)
            logger.debug("Screen and stream created successfully")

            # Test basic output
            logger.debug("Testing basic output")
            try:
                logger.debug("Feeding basic text to stream")
                stream.feed("hello\nworld\n")
                logger.debug("Stream feed complete")
                self.assertEqual([line.strip() for line in screen.display[:2]], ["hello", "world"])
            except Exception as e:
                logger.error(f"Error in basic output test: {e}")
                raise

            # Reset screen
            screen = mock_pyte_screen()
            stream = mock_pyte_stream(screen)

            # Test ANSI color codes
            logger.debug("Testing ANSI color codes")
            try:
                stream.feed("\x1b[31mRed\x1b[0m \x1b[32mGreen\x1b[0m\n")
                logger.debug("ANSI codes processed")
                self.assertEqual(screen.display[0].strip().replace("  ", " "), "Red Green")
            except Exception as e:
                logger.error(f"Error in ANSI color test: {e}")
                raise

            # Reset screen
            screen = mock_pyte_screen()
            stream = mock_pyte_stream(screen)

            # Test cursor movement
            logger.debug("Testing cursor movement")
            try:
                stream.feed("First\rSecond\nThird\n")
                self.assertEqual(screen.display[0].strip(), "Second")
                self.assertEqual(screen.display[1].strip(), "Third")
            except Exception as e:
                logger.error(f"Error in cursor movement test: {e}")
                raise

            # Reset screen
            screen = mock_pyte_screen()
            stream = mock_pyte_stream(screen)

            # Test line clearing
            logger.debug("Testing line clearing")
            try:
                stream.feed("Line1\x1b[2K\rLine2\n")
                self.assertEqual(screen.display[0].strip(), "Line2")
            except Exception as e:
                logger.error(f"Error in line clearing test: {e}")
                raise

        except Exception as e:
            logger.error(f"Error in render_terminal_output test: {e}")
            raise
        finally:
            logger.info("Completed render_terminal_output test")

    def test_incremental_text(self):
        """Test incremental text extraction"""
        # Test with empty old output
        with patch('wcgw.client.tools.render_terminal_output', side_effect=lambda x: x.rstrip().split('\n')):
            result = _incremental_text("line1\nline2\n", "")
            self.assertEqual(result, "line1\nline2")

        # Test with one line in old output
        with patch('wcgw.client.tools.render_terminal_output') as mock_render:
            mock_render.side_effect = [
                ["line1"], # First call for last_pending_output
                ["line1", "line2"]  # Second call for old_rendered_applied
            ]
            result = _incremental_text("line1\nline2\n", "line1\n")
            self.assertEqual(result, "line2")

        # Test with overlapping content 
        with patch('wcgw.client.tools.render_terminal_output') as mock_render:
            mock_render.side_effect = [
                ["line1", "line2"],  # Last pending output rendered  
                ["line1", "line2", "line3"]   # Combined text rendered
            ]
            # The implementation will:
            # 1. Render last pending (["line1", "line2"])
            # 2. Join it ("\nline1\nline2")
            # 3. Append new text ("line1\nline2\nline3")
            # 4. Look for incremental output by comparing last_rendered_lines[:-1] with new_rendered
            result = _incremental_text("line3\n", "line1\nline2\n")
            self.assertEqual(result, "line3")

        # Test with completely different content
        with patch('wcgw.client.tools.render_terminal_output') as mock_render:
            mock_render.side_effect = [
                ["old content"],              # First call - render old pending output
                ["old content", "new content"] # Second call - render old + new
            ]
            result = _incremental_text("new content\n", "old content\n")
            self.assertEqual(result, "new content")

        # Test with empty new text
        with patch('wcgw.client.tools.render_terminal_output', side_effect=lambda x: x.rstrip().split('\n')):
            result = _incremental_text("", "some old content\n")
            self.assertEqual(result, "")

    def test_get_incremental_output(self):
        """Test getting incremental output from terminal"""
        # Test with empty old output
        old_output = []
        new_output = ["line1", "line2"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, new_output)

        # Test with completely different output
        old_output = ["old"]
        new_output = ["new"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, new_output)

        # Test with overlapping content
        old_output = ["line1", "line2"]
        new_output = ["line1", "line2", "line3"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, ["line3"])

        # Test with no new content
        old_output = ["line1", "line2"]
        new_output = ["line1", "line2"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, [])

if __name__ == '__main__':
    unittest.main()