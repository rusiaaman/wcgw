"""
Tests for the token counter module
"""

import unittest
from unittest.mock import MagicMock

from wcgw.token_counter import TokenCounter

class TestTokenCounter(unittest.TestCase):
    """Test the TokenCounter class."""

    def test_count_tokens(self) -> None:
        """Test the count_tokens method."""
        # Setup
        counter = TokenCounter(max_tokens=100000, token_threshold=0.9, auto_continue=False)

        # Execute
        result = counter.count_tokens("Test message")

        # Assert
        self.assertGreater(result, 0)  # Should return a positive number of tokens

    def test_count_message(self) -> None:
        """Test counting tokens in a message."""
        # Setup
        counter = TokenCounter(max_tokens=100000, token_threshold=0.9, auto_continue=False)

        # Mock the count_tokens method
        counter.count_tokens = MagicMock(return_value=10)

        # Execute
        result = counter.count_message("Test message")

        # Assert
        counter.count_tokens.assert_called_once_with("Test message")
        self.assertEqual(result, 10)

    def test_add_prompt(self) -> None:
        """Test adding prompt tokens."""
        # Setup
        counter = TokenCounter(max_tokens=100000, token_threshold=0.9, auto_continue=False)

        # Mock the count_message method
        counter.count_message = MagicMock(return_value=15)

        # Execute
        result = counter.add_prompt("Test prompt")

        # Assert
        self.assertEqual(result, 15)
        self.assertEqual(counter.prompt_tokens, 15)
        self.assertEqual(counter.conversation_tokens, 15)

    def test_add_completion(self) -> None:
        """Test adding completion tokens."""
        # Setup
        counter = TokenCounter(max_tokens=100000, token_threshold=0.9, auto_continue=False)

        # Mock the count_message method
        counter.count_message = MagicMock(return_value=25)

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
