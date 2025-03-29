"""
Integration utilities for adding token tracking to the MCP server
"""

import logging
import functools
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')
ServerClass = TypeVar('ServerClass')

def enhance_mcp_server(server_class: type[T]) -> type[T]:
    """
    Decorator to enhance an MCP server class with token tracking
    This is a non-invasive way to add token tracking to existing server implementations
    """

    # Store original methods that we'll enhance
    original_init = server_class.__init__

    @functools.wraps(original_init)
    def enhanced_init(self: Any, *args: Any, **kwargs: Any) -> None:
        # Call original init
        original_init(self, *args, **kwargs)

        # Import here to avoid circular imports
        from .token_handler import TokenHandler

        # Add token handler with empty config if not available
        config = getattr(self, 'config', {})
        self._token_handler = TokenHandler(config)

        # Enhance initial config
        if hasattr(self, 'config'):
            self.config = self._token_handler.enhance_config(self.config)

    # Add enhancement methods
    add_initialize_method(server_class)
    add_request_method(server_class)
    add_response_method(server_class)
    add_token_tracker_accessor(server_class)

    # Replace init method
    server_class.__init__ = enhanced_init

    return server_class

def add_initialize_method(server_class: type) -> None:
    """Add enhanced initialize method if it exists"""
    if hasattr(server_class, 'initialize'):
        original_initialize = server_class.initialize

        def enhanced_initialize(self: Any, config_update: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            # Call original initialize
            result = original_initialize(self, config_update, *args, **kwargs)

            # Update token handler config
            self._token_handler.update_config(config_update)

            return result

        server_class.initialize = enhanced_initialize

def add_request_method(server_class: type) -> None:
    """Add enhanced process_request method if it exists"""
    if hasattr(server_class, 'process_request'):
        original_process_request = server_class.process_request

        def enhanced_process_request(self: Any, request: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            # Process request with token handler
            processed_request = self._token_handler.process_request(request)

            # Call original process_request
            return original_process_request(self, processed_request, *args, **kwargs)

        server_class.process_request = enhanced_process_request

def add_response_method(server_class: type) -> None:
    """Add enhanced process_response method if it exists"""
    if hasattr(server_class, 'process_response'):
        original_process_response = server_class.process_response

        def enhanced_process_response(self: Any, response: dict[str, Any], request: dict[str, Any],
                                    *args: Any, **kwargs: Any) -> dict[str, Any]:
            # Call original process_response
            original_result = original_process_response(self, response, request, *args, **kwargs)

            # Process response with token handler
            processed_response = self._token_handler.process_response(original_result, request)

            # Handle auto-continue if needed
            if processed_response.get('auto_continued') and hasattr(self, 'queue_request'):
                # Create a continue request
                continue_request = {
                    "type": "continue",
                    "prompt": "Continue",
                    "is_auto_continue": True
                }

                try:
                    self.queue_request(continue_request)
                    tokens = self._token_handler.token_tracker.conversation_tokens
                    max_tokens = self._token_handler.token_tracker.max_tokens
                    logger.info(f"Auto-continuing. Tokens: {tokens}/{max_tokens}")
                except Exception as e:
                    logger.error(f"Error scheduling auto-continue: {e}")

            return processed_response

        server_class.process_response = enhanced_process_response

def add_token_tracker_accessor(server_class: type) -> None:
    """Add direct access to token tracker"""
    def get_token_tracker(self: Any) -> Any:
        return self._token_handler.token_tracker

    server_class.get_token_tracker = get_token_tracker

def enhance_server_instance(server: Any) -> Any:
    """
    Enhance an existing server instance with token tracking
    This is for when you can't modify the class but want to enhance an instance
    """
    # Import here to avoid circular imports
    from .token_handler import TokenHandler

    # Create handler with empty config if not available
    config = getattr(server, 'config', {})
    token_handler = TokenHandler(config)

    # Enhance the config
    if hasattr(server, 'config'):
        server.config = token_handler.enhance_config(server.config)

    # Store token handler on the instance
    server._token_handler = token_handler

    # Add methods if they exist
    if hasattr(server, 'initialize'):
        original_initialize = server.initialize

        def enhanced_initialize(config_update: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            # Call original method
            result = original_initialize(config_update, *args, **kwargs)

            # Update token handler config
            token_handler.update_config(config_update)

            return result

        server.initialize = enhanced_initialize.__get__(server)

    if hasattr(server, 'process_request'):
        original_process_request = server.process_request

        def enhanced_process_request(request: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            # Process request with token handler
            processed_request = token_handler.process_request(request)

            # Call original method
            return original_process_request(processed_request, *args, **kwargs)

        server.process_request = enhanced_process_request.__get__(server)

    if hasattr(server, 'process_response'):
        original_process_response = server.process_response

        def enhanced_process_response(response: dict[str, Any], request: dict[str, Any],
                                    *args: Any, **kwargs: Any) -> dict[str, Any]:
            # Call original method
            original_result = original_process_response(response, request, *args, **kwargs)

            # Process response with token handler
            processed_response = token_handler.process_response(original_result, request)

            # Handle auto-continue
            if processed_response.get('auto_continued') and hasattr(server, 'queue_request'):
                try:
                    server.queue_request({
                        "type": "continue",
                        "prompt": "Continue",
                        "is_auto_continue": True
                    })
                    tokens = token_handler.token_tracker.conversation_tokens
                    max_tokens = token_handler.token_tracker.max_tokens
                    logger.info(f"Auto-continuing. Tokens: {tokens}/{max_tokens}")
                except Exception as e:
                    logger.error(f"Error scheduling auto-continue: {e}")

            return processed_response

        server.process_response = enhanced_process_response.__get__(server)

    # Add access to token tracker
    server.get_token_tracker = lambda: token_handler.token_tracker

    return server
