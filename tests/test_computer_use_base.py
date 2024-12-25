"""Tests for computer_use.py core functionality"""

import pytest
from wcgw.client.computer_use import (
    ToolResult,
    CLIResult,
    ToolFailure,
    ToolError,
    ComputerTool,
    ScalingSource,
    chunks,
)


def test_tool_result_initialization():
    # Test empty initialization
    result = ToolResult()
    assert not bool(result)
    
    # Test with output only
    result = ToolResult(output="test output")
    assert bool(result)
    assert result.output == "test output"
    assert result.error is None
    assert result.base64_image is None
    assert result.system is None

    # Test with all fields
    result = ToolResult(
        output="test output",
        error="test error",
        base64_image="base64string",
        system="test system"
    )
    assert bool(result)
    assert result.output == "test output"
    assert result.error == "test error"
    assert result.base64_image == "base64string"
    assert result.system == "test system"


def test_tool_result_addition():
    result1 = ToolResult(output="output1", error="error1")
    result2 = ToolResult(output="output2", error="error2")
    
    combined = result1 + result2
    assert combined.output == "output1output2"
    assert combined.error == "error1error2"
    assert combined.base64_image is None
    assert combined.system is None


def test_tool_result_addition_with_base64():
    result1 = ToolResult(base64_image="image1")
    result2 = ToolResult(base64_image="image2")
    
    with pytest.raises(ValueError, match="Cannot combine tool results"):
        _ = result1 + result2


def test_tool_result_replace():
    result = ToolResult(output="test")
    new_result = result.replace(output="new test")
    assert new_result.output == "new test"
    assert new_result is not result


def test_cli_result_inheritance():
    cli_result = CLIResult(output="cli test")
    assert isinstance(cli_result, ToolResult)
    assert cli_result.output == "cli test"


def test_tool_failure_inheritance():
    failure = ToolFailure(error="test error")
    assert isinstance(failure, ToolResult)
    assert failure.error == "test error"


def test_tool_error():
    error = ToolError("test error")
    assert error.message == "test error"


def test_chunks_function():
    # Test with exact chunk size
    assert chunks("123456", 2) == ["12", "34", "56"]
    
    # Test with incomplete last chunk
    assert chunks("12345", 2) == ["12", "34", "5"]
    
    # Test with chunk size larger than string
    assert chunks("123", 5) == ["123"]
    
    # Test empty string
    assert chunks("", 2) == []


def test_computer_tool_initialization():
    tool = ComputerTool()
    assert tool.name == "computer"
    assert tool.width is None
    assert tool.height is None
    assert tool.display_num is None
    assert tool.xdotool is None
    assert tool.docker_image_id is None
    assert tool._display_prefix == ""


def test_scale_coordinates_errors():
    tool = ComputerTool()
    
    # Test without screen info
    with pytest.raises(ToolError, match="Please first get screen info using get_screen_info tool"):
        tool.scale_coordinates(ScalingSource.API, 100, 100)

    # Set screen dimensions
    tool.width = 1920
    tool.height = 1080

    # Test out of bounds coordinates
    with pytest.raises(ToolError, match="Coordinates 2000, 100 are out of bounds"):
        tool.scale_coordinates(ScalingSource.API, 2000, 100)
