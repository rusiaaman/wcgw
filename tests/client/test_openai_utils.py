import pytest
from typing import cast
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageParam, ParsedChatCompletionMessage
from tokenizers import Tokenizer
from wcgw.client.openai_utils import get_input_cost, get_output_cost
from wcgw.client.common import CostData


@pytest.fixture
def tokenizer():
    # Create a simple tokenizer for testing
    return Tokenizer.from_pretrained("gpt2")


@pytest.fixture
def cost_data():
    return CostData(
        cost_per_1m_input_tokens=0.01,
        cost_per_1m_output_tokens=0.03
    )


def test_get_input_cost_simple(tokenizer, cost_data):
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"}
    ]
    cost, tokens = get_input_cost(cost_data, tokenizer, history)
    assert tokens > 0
    assert cost > 0


def test_get_input_cost_with_list_content(tokenizer, cost_data):
    history = [
        {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
        {"role": "assistant", "content": "Hi there"}
    ]
    cost, tokens = get_input_cost(cost_data, tokenizer, history)
    assert tokens > 0
    assert cost > 0


def test_get_input_cost_with_refusal(tokenizer, cost_data):
    history = [
        {"role": "user", "content": None, "refusal": "Content refused"},
        {"role": "assistant", "content": "Hi there"}
    ]
    cost, tokens = get_input_cost(cost_data, tokenizer, history)
    assert tokens > 0
    assert cost > 0


def test_get_input_cost_invalid_content():
    cost_data = CostData(cost_per_1m_input_tokens=0.01, cost_per_1m_output_tokens=0.03)
    tokenizer = Tokenizer.from_pretrained("gpt2")
    history = [{"role": "user", "content": 123}]  # type: ignore
    
    with pytest.raises(ValueError, match="Expected content to be string"):
        get_input_cost(cost_data, tokenizer, history)


def test_get_output_cost_simple_message(tokenizer, cost_data):
    message = ChatCompletionMessage(
        content="Hello world",
        role="assistant",
        tool_calls=None
    )
    cost, tokens = get_output_cost(cost_data, tokenizer, message)
    assert tokens > 0
    assert cost > 0


def test_get_output_cost_with_tool_calls(tokenizer, cost_data):
    message = {
        "role": "assistant",
        "content": "Let me help you with that",
        "tool_calls": [
            {
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "test_function",
                    "arguments": '{"arg1": "test"}'
                }
            }
        ]
    }
    cost, tokens = get_output_cost(cost_data, tokenizer, cast(ChatCompletionMessageParam, message))
    assert tokens > 0
    assert cost > 0


def test_get_output_cost_tool_message(tokenizer, cost_data):
    message = {
        "role": "tool",
        "content": "Tool execution result",
        "tool_call_id": "call_123"
    }
    cost, tokens = get_output_cost(cost_data, tokenizer, cast(ChatCompletionMessageParam, message))
    assert cost == 0
    assert tokens == 0