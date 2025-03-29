"""
Token tracker for MCP server
"""

import logging
from typing import Any

from ...token_counter import TokenCounter

class TokenTracker:
    """Token tracking for MCP server, integrates with TokenCounter"""

    def __init__(self, max_tokens: int, token_threshold: float, auto_continue: bool) -> None:
        """Initialize the token tracker"""
        self.logger = logging.getLogger(__name__)
        self.counter = TokenCounter(
            max_tokens=max_tokens,
            token_threshold=token_threshold,
            auto_continue=auto_continue
        )

    @property
    def max_tokens(self) -> int:
        """Get max tokens"""
        return self.counter.max_tokens

    @max_tokens.setter
    def max_tokens(self, value: int) -> None:
        """Set max tokens"""
        self.counter.max_tokens = value

    @property
    def token_threshold(self) -> float:
        """Get token threshold"""
        return self.counter.token_threshold

    @token_threshold.setter
    def token_threshold(self, value: float) -> None:
        """Set token threshold"""
        self.counter.token_threshold = value

    @property
    def auto_continue(self) -> bool:
        """Get auto continue setting"""
        return self.counter.auto_continue

    @auto_continue.setter
    def auto_continue(self, value: bool) -> None:
        """Set auto continue setting"""
        self.counter.auto_continue = value

    @property
    def conversation_tokens(self) -> int:
        """Get conversation tokens"""
        return self.counter.conversation_tokens

    def add_prompt(self, prompt: str) -> int:
        """Add prompt tokens"""
        return self.counter.add_prompt(prompt)

    def add_completion(self, completion: str) -> int:
        """Add completion tokens"""
        return self.counter.add_completion(completion)

    def update_max_tokens(self, max_tokens: int) -> None:
        """Update max tokens from API"""
        self.counter.update_max_tokens(max_tokens)

    def get_usage(self) -> dict[str, Any]:
        """Get token usage stats"""
        return self.counter.get_usage()

    def should_auto_continue(self) -> bool:
        """Check if we should auto-continue"""
        return self.counter.should_auto_continue()

    def reset(self) -> None:
        """Reset counters"""
        self.counter.reset()
