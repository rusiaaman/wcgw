"""Tests for the token counter module."""

import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add the src directory to the path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from wcgw.token_counter import TokenCounter

class TestTokenCounter(unittest.TestCase):
    """Test the TokenCounter class."""

    @patch('wcgw.token_counter.count_tokens')
    def test_count_message(self, mock_count_tokens: MagicMock) -> None:
        """Test counting tokens in a message."""
        # Setup
        mock_count_tokens.return_value = 10
        counter = TokenCounter(max_tokens=100000, token_threshold=0.9, auto_continue=False)

        # Execute
        result = counter.count_message("Test message")

        # Assert
        mock_count_tokens.assert_called_once_with("Test message")
        self.assertEqual(result, 10)

    @patch('wcgw.token_counter.count_tokens')
    def test_add_prompt(self, mock_count_tokens: MagicMock) -> None:
        """Test adding prompt tokens."""
        # Setup
        mock_count_tokens.return_value = 15
        counter = TokenCounter(max_tokens=100000, token_threshold=0.9, auto_continue=False)

        # Execute
        result = counter.add_prompt("Test prompt")

        # Assert
        self.assertEqual(result, 15)
        self.assertEqual(counter.prompt_tokens, 15)
        self.assertEqual(counter.conversation_tokens, 15)

    @patch('wcgw.token_counter.count_tokens')
    def test_add_completion(self, mock_count_tokens: MagicMock) -> None:
        """Test adding completion tokens."""
        # Setup
        mock_count_tokens.return_value = 25
        counter = TokenCounter(max_tokens=100000, token_threshold=0.9, auto_continue=False)

        # Execute
        result = counter.add_completion("Test completion")

        # Assert
        self.assertEqual(result, 25)
        self.assertEqual(counter.completion_tokens, 25)
        self.assertEqual(counter.conversation_tokens, 25)

    def test_get_usage(self) -> None:
        """Test getting usage stats."""
        # Setup
        counter = TokenCounter(max_tokens=1000, token_threshold=0.9, auto_continue=False)
        counter.prompt_tokens = 100
        counter.completion_tokens = 200
        counter.conversation_tokens = 300

        # Execute
        usage = counter.get_usage()

        # Assert
        self.assertEqual(usage["prompt_tokens"], 100)
        self.assertEqual(usage["completion_tokens"], 200)
        self.assertEqual(usage["total_tokens"], 300)
        self.assertEqual(usage["total_tokens_kb"], 0.3)
        self.assertEqual(usage["token_max_size_kb"], 1.0)
        self.assertEqual(usage["usage_percentage"], 0.3)

    def test_should_auto_continue_disabled(self) -> None:
        """Test auto-continue when disabled."""
        # Setup
        counter = TokenCounter(max_tokens=100000, token_threshold=0.9, auto_continue=False)

        # Execute & Assert
        self.assertFalse(counter.should_auto_continue())

    def test_should_auto_continue_below_threshold(self) -> None:
        """Test auto-continue when below threshold."""
        # Setup
        counter = TokenCounter(max_tokens=1000, token_threshold=0.9, auto_continue=True)
        counter.conversation_tokens = 800  # 80% of max

        # Execute & Assert
        self.assertTrue(counter.should_auto_continue())

    def test_should_auto_continue_above_threshold(self) -> None:
        """Test auto-continue when above threshold."""
        # Setup
        counter = TokenCounter(max_tokens=1000, token_threshold=0.9, auto_continue=True)
        counter.conversation_tokens = 950  # 95% of max

        # Execute & Assert
        self.assertFalse(counter.should_auto_continue())

    def test_reset(self) -> None:
        """Test resetting counters."""
        # Setup
        counter = TokenCounter(max_tokens=100000, token_threshold=0.9, auto_continue=False)
        counter.prompt_tokens = 100
        counter.completion_tokens = 200
        counter.conversation_tokens = 300

        # Execute
        counter.reset()

        # Assert
        self.assertEqual(counter.prompt_tokens, 0)
        self.assertEqual(counter.completion_tokens, 0)
        self.assertEqual(counter.conversation_tokens, 0)

    def test_update_max_tokens(self) -> None:
        """Test updating max tokens."""
        # Setup
        counter = TokenCounter(max_tokens=1000, token_threshold=0.9, auto_continue=False)

        # Execute
        counter.update_max_tokens(2000)

        # Assert
        self.assertEqual(counter.max_tokens, 2000)

if __name__ == '__main__':
    unittest.main()
