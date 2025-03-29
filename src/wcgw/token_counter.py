"""
Token counter module for tracking token usage in Claude conversations
"""

import logging
from typing import Any
import tiktoken

class TokenCounter:
    """Track token usage across a conversation"""

    def __init__(self, max_tokens: int, token_threshold: float, auto_continue: bool) -> None:
        self.max_tokens = max_tokens
        self.token_threshold = token_threshold
        self.auto_continue = auto_continue
        self.logger = logging.getLogger("token_counter")
        self.conversation_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

    def reset(self) -> None:
        """Reset token counters"""
        self.conversation_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text using tiktoken"""
        if not text:
            return 0
        return len(self._tokenizer.encode(text))

    def count_message(self, text: str) -> int:
        """Count tokens in a message"""
        if not text:
            return 0
        return self.count_tokens(text)

    def add_prompt(self, prompt: str) -> int:
        """Count and record prompt tokens"""
        tokens = self.count_message(prompt)
        self.prompt_tokens += tokens
        self.conversation_tokens += tokens
        return tokens

    def add_completion(self, completion: str) -> int:
        """Count and record completion tokens"""
        tokens = self.count_message(completion)
        self.completion_tokens += tokens
        self.conversation_tokens += tokens
        return tokens

    def update_max_tokens(self, max_tokens: int) -> None:
        """Update max_tokens with value from API"""
        if max_tokens > 0:
            self.logger.info(f"Updating max_tokens from {self.max_tokens} to {max_tokens}")
            self.max_tokens = max_tokens

    def get_usage(self) -> dict[str, Any]:
        """Get current token usage stats"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.conversation_tokens,
            "total_tokens_kb": round(self.conversation_tokens / 1000, 1),
            "token_max_size_kb": round(self.max_tokens / 1000, 1),
            "usage_percentage": self.conversation_tokens / self.max_tokens
        }

    def should_auto_continue(self) -> bool:
        """Determine if we should auto-continue based on token threshold and auto_continue setting"""
        if not self.auto_continue:
            return False
        return self.conversation_tokens < (self.max_tokens * self.token_threshold)