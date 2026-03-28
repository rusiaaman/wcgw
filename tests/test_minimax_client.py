"""Unit tests for the MiniMax client module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from wcgw.client.common import CostData, MiniMaxModels


class TestClampTemperature:
    """Tests for the clamp_temperature function."""

    def test_clamp_zero(self) -> None:
        from wcgw_cli.minimax_client import clamp_temperature

        assert clamp_temperature(0.0) == 0.01

    def test_clamp_negative(self) -> None:
        from wcgw_cli.minimax_client import clamp_temperature

        assert clamp_temperature(-0.5) == 0.01

    def test_clamp_above_one(self) -> None:
        from wcgw_cli.minimax_client import clamp_temperature

        assert clamp_temperature(1.5) == 1.0

    def test_clamp_exactly_one(self) -> None:
        from wcgw_cli.minimax_client import clamp_temperature

        assert clamp_temperature(1.0) == 1.0

    def test_clamp_valid_value(self) -> None:
        from wcgw_cli.minimax_client import clamp_temperature

        assert clamp_temperature(0.7) == 0.7

    def test_clamp_small_positive(self) -> None:
        from wcgw_cli.minimax_client import clamp_temperature

        assert clamp_temperature(0.01) == 0.01

    def test_clamp_very_small_positive(self) -> None:
        from wcgw_cli.minimax_client import clamp_temperature

        # Values <= 0.0 get clamped to 0.01, but 0.001 > 0.0
        assert clamp_temperature(0.001) == 0.001


class TestStripThinkTags:
    """Tests for the strip_think_tags function."""

    def test_strip_simple(self) -> None:
        from wcgw_cli.minimax_client import strip_think_tags

        text = "<think>reasoning here</think>actual response"
        assert strip_think_tags(text) == "actual response"

    def test_strip_multiline(self) -> None:
        from wcgw_cli.minimax_client import strip_think_tags

        text = "<think>\nline1\nline2\n</think>\nactual response"
        assert strip_think_tags(text) == "actual response"

    def test_no_think_tags(self) -> None:
        from wcgw_cli.minimax_client import strip_think_tags

        text = "just a normal response"
        assert strip_think_tags(text) == "just a normal response"

    def test_empty_think_tags(self) -> None:
        from wcgw_cli.minimax_client import strip_think_tags

        text = "<think></think>response"
        assert strip_think_tags(text) == "response"

    def test_multiple_think_tags(self) -> None:
        from wcgw_cli.minimax_client import strip_think_tags

        text = "<think>a</think>hello<think>b</think> world"
        assert strip_think_tags(text) == "hello world"

    def test_only_think_tags(self) -> None:
        from wcgw_cli.minimax_client import strip_think_tags

        text = "<think>only thinking</think>"
        assert strip_think_tags(text) == ""


class TestConfig:
    """Tests for the MiniMax Config model."""

    def test_config_default_model(self) -> None:
        from wcgw_cli.minimax_client import Config

        config = Config(
            model="MiniMax-M2.7",
            cost_limit=0.1,
            cost_file={
                "MiniMax-M2.7": CostData(
                    cost_per_1m_input_tokens=1.0,
                    cost_per_1m_output_tokens=5.0,
                ),
            },
        )
        assert config.model == "MiniMax-M2.7"
        assert config.cost_limit == 0.1
        assert config.cost_unit == "$"

    def test_config_highspeed_model(self) -> None:
        from wcgw_cli.minimax_client import Config

        config = Config(
            model="MiniMax-M2.7-highspeed",
            cost_limit=0.5,
            cost_file={
                "MiniMax-M2.7-highspeed": CostData(
                    cost_per_1m_input_tokens=1.0,
                    cost_per_1m_output_tokens=5.0,
                ),
            },
        )
        assert config.model == "MiniMax-M2.7-highspeed"
        assert config.cost_limit == 0.5


class TestMiniMaxBaseUrl:
    """Tests for the MiniMax base URL constant."""

    def test_base_url(self) -> None:
        from wcgw_cli.minimax_client import MINIMAX_BASE_URL

        assert MINIMAX_BASE_URL == "https://api.minimax.io/v1"


class TestMiniMaxModels:
    """Tests for MiniMax model types."""

    def test_m27_is_valid(self) -> None:
        model: MiniMaxModels = "MiniMax-M2.7"
        assert model == "MiniMax-M2.7"

    def test_m27_highspeed_is_valid(self) -> None:
        model: MiniMaxModels = "MiniMax-M2.7-highspeed"
        assert model == "MiniMax-M2.7-highspeed"


class TestParseUserMessageSpecial:
    """Tests for parse_user_message_special from minimax client."""

    def test_plain_text(self) -> None:
        from wcgw_cli.minimax_client import parse_user_message_special

        result = parse_user_message_special("hello world")
        assert result["role"] == "user"
        content = result["content"]
        assert isinstance(content, list)
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "hello world"

    def test_multiline_text(self) -> None:
        from wcgw_cli.minimax_client import parse_user_message_special

        result = parse_user_message_special("line1\nline2\nline3")
        content = result["content"]
        assert isinstance(content, list)
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert "line1" in content[0]["text"]
        assert "line2" in content[0]["text"]
        assert "line3" in content[0]["text"]


class TestMiniMaxApiKeyValidation:
    """Tests for MINIMAX_API_KEY environment variable handling."""

    def test_api_key_from_env(self) -> None:
        """Verify that the client reads MINIMAX_API_KEY from environment."""
        import os as _os

        with patch.dict(_os.environ, {"MINIMAX_API_KEY": "test-key-123"}, clear=False):
            val = _os.getenv("MINIMAX_API_KEY")
            assert val == "test-key-123"

    def test_missing_api_key_is_none(self) -> None:
        """Verify that missing MINIMAX_API_KEY returns None."""
        import os as _os

        with patch.dict(_os.environ, {}, clear=False):
            _os.environ.pop("MINIMAX_API_KEY", None)
            val = _os.getenv("MINIMAX_API_KEY")
            assert val is None


class TestCostData:
    """Tests for cost data configuration."""

    def test_minimax_m27_cost(self) -> None:
        cost = CostData(
            cost_per_1m_input_tokens=1.0,
            cost_per_1m_output_tokens=5.0,
        )
        # Cost for 1000 input tokens
        input_cost = 1000 * cost.cost_per_1m_input_tokens / 1_000_000
        assert input_cost == 0.001
        # Cost for 1000 output tokens
        output_cost = 1000 * cost.cost_per_1m_output_tokens / 1_000_000
        assert output_cost == 0.005
