"""Integration tests for MiniMax client with MiniMax API.

These tests require a valid MINIMAX_API_KEY environment variable.
They are skipped if the API key is not available.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("MINIMAX_API_KEY"),
    reason="MINIMAX_API_KEY not set",
)


class TestMiniMaxAPIConnection:
    """Integration tests that verify MiniMax API connectivity."""

    def test_minimax_client_creation(self) -> None:
        """Test that we can create an OpenAI client pointed at MiniMax."""
        from openai import OpenAI

        from wcgw_cli.minimax_client import MINIMAX_BASE_URL

        client = OpenAI(
            api_key=os.environ["MINIMAX_API_KEY"],
            base_url=MINIMAX_BASE_URL,
        )
        assert client.base_url is not None

    def test_minimax_simple_completion(self) -> None:
        """Test a simple chat completion via MiniMax API."""
        from openai import OpenAI

        from wcgw_cli.minimax_client import MINIMAX_BASE_URL

        client = OpenAI(
            api_key=os.environ["MINIMAX_API_KEY"],
            base_url=MINIMAX_BASE_URL,
        )
        response = client.chat.completions.create(
            model="MiniMax-M2.7",
            messages=[{"role": "user", "content": "Say 'hello' and nothing else."}],
            max_tokens=100,
            temperature=0.01,
        )
        content = response.choices[0].message.content
        assert content is not None
        # The response may include <think> tags; verify we got content
        assert len(content) > 0

    def test_minimax_streaming(self) -> None:
        """Test streaming chat completion via MiniMax API."""
        from openai import OpenAI

        from wcgw_cli.minimax_client import MINIMAX_BASE_URL

        client = OpenAI(
            api_key=os.environ["MINIMAX_API_KEY"],
            base_url=MINIMAX_BASE_URL,
        )
        stream = client.chat.completions.create(
            model="MiniMax-M2.7-highspeed",
            messages=[{"role": "user", "content": "Say 'test' and nothing else."}],
            max_tokens=50,
            temperature=0.01,
            stream=True,
        )
        chunks = list(stream)
        assert len(chunks) > 0
        # At least one chunk should have content
        contents = [
            c.choices[0].delta.content
            for c in chunks
            if c.choices[0].delta.content
        ]
        assert len(contents) > 0
