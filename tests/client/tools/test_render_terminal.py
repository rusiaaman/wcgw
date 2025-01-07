import pytest
from wcgw.client.tools import render_terminal_output
import pyte

def test_render_terminal_output_basic():
    """Test basic terminal output rendering"""
    test_text = "Hello\nWorld"
    lines = render_terminal_output(test_text)
    assert [line.strip() for line in lines] == ["Hello", "World"]

def test_render_terminal_output_ansi():
    """Test rendering with ANSI escape sequences"""
    test_text = "\033[31mRed\033[0m\n\033[32mGreen\033[0m"
    lines = render_terminal_output(test_text)
    assert [line.strip() for line in lines] == ["Red", "Green"]

def test_render_terminal_output_empty():
    """Test handling of empty input"""
    assert render_terminal_output("") == []

def test_render_terminal_output_exception():
    """Test exception handling by providing invalid input"""
    # Should handle non-string input by raising TypeError/AttributeError
    with pytest.raises((TypeError, AttributeError)):
        render_terminal_output(123)