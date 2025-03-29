"""
Token handler for MCP server
"""

import logging
from typing import Any
from .token_tracker import TokenTracker

class TokenHandler:
    """
    Handles token tracking functionality for MCP server
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the handler"""
        self.logger = logging.getLogger(__name__)
        self._config = config

        # Initialize token tracker with default values if not in config
        max_tokens = config.get('max_tokens', 100000)
        token_threshold = config.get('token_threshold', 0.9)
        auto_continue = config.get('continue', False)

        self.token_tracker = TokenTracker(
            max_tokens=max_tokens,
            token_threshold=token_threshold,
            auto_continue=auto_continue
        )

    def enhance_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Add token tracking config to existing config"""
        enhanced_config = config.copy()

        # Add default token tracking config if not present
        if 'max_tokens' not in enhanced_config:
            enhanced_config['max_tokens'] = 100000
        if 'token_threshold' not in enhanced_config:
            enhanced_config['token_threshold'] = 0.9
        if 'continue' not in enhanced_config:
            enhanced_config['continue'] = False

        return enhanced_config

    def update_config(self, config: dict[str, Any]) -> None:
        """Update token tracker config when server config is updated"""
        self._config.update(config)

        # Update token tracker settings
        if 'max_tokens' in config:
            self.token_tracker.max_tokens = config['max_tokens']
        if 'token_threshold' in config:
            self.token_tracker.token_threshold = config['token_threshold']
        if 'continue' in config:
            self.token_tracker.auto_continue = config['continue']
            self.logger.info(f"Auto-continue setting updated to: {self.token_tracker.auto_continue}")

    def process_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Process request and track tokens"""
        prompt = request.get('prompt', '')
        self.token_tracker.add_prompt(prompt)
        return request

    def process_response(self, response: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        """Process response and track tokens"""
        # Extract max_tokens from API response if available
        if 'usage' in response and 'max_tokens_in_context' in response['usage']:
            self.token_tracker.update_max_tokens(response['usage']['max_tokens_in_context'])

        # If response contains completion, count tokens
        completion = response.get('completion', '')
        if completion:
            self.token_tracker.add_completion(completion)

        # Add token usage information to the response
        response['token_usage'] = self.token_tracker.get_usage()

        # Check if Claude has hit its message length limit
        message_limit_reached = (completion and
                "Claude hit the max length for a message and has paused its response." in completion)

        if message_limit_reached and self.token_tracker.should_auto_continue():
            # Add a flag to indicate auto-continue
            response['auto_continued'] = True

        return response

    def should_auto_continue(self, completion: str) -> bool:
        """Check if auto-continue should be triggered"""
        # Ensure we return a boolean
        has_limit_message = "Claude hit the max length for a message and has paused its response." in completion
        return bool(completion and has_limit_message and self.token_tracker.should_auto_continue())
