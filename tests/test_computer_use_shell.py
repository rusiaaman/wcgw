"""Tests for computer_use.py shell and screenshot functionality"""

import pytest
from unittest.mock import patch, MagicMock
from wcgw.client.computer_use import ComputerTool, ToolError


@pytest.fixture
def mock_command_run():
    with patch("wcgw.client.computer_use.command_run") as mock:
        mock.return_value = (0, "test output", "test error")
        yield mock


@pytest.fixture
def initialized_tool():
    tool = ComputerTool()
    tool.docker_image_id = "test_docker_id"
    tool.width = 1920
    tool.height = 1080
    tool._display_prefix = "DISPLAY=:0 "
    tool.xdotool = "DISPLAY=:0 xdotool"
    return tool


def test_get_screen_info_success(mock_command_run):
    mock_command_run.return_value = (0, "1920,1080,0\n", "")
    tool = ComputerTool()
    tool.docker_image_id = "test_docker_id"

    width, height, display_num = tool.get_screen_info()
    
    assert width == 1920
    assert height == 1080
    assert display_num == 0
    assert tool.width == 1920
    assert tool.height == 1080
    assert tool.display_num == 0
    assert tool._display_prefix == "DISPLAY=:0 "
    assert tool.xdotool == "DISPLAY=:0 xdotool"


def test_get_screen_info_no_display(mock_command_run):
    mock_command_run.return_value = (0, "1920,1080,\n", "")
    tool = ComputerTool()
    tool.docker_image_id = "test_docker_id"

    width, height, display_num = tool.get_screen_info()
    
    assert width == 1920
    assert height == 1080
    assert display_num is None
    assert tool._display_prefix == ""


def test_get_screen_info_defaults(mock_command_run):
    mock_command_run.return_value = (0, ",,\n", "")
    tool = ComputerTool()
    tool.docker_image_id = "test_docker_id"

    width, height, display_num = tool.get_screen_info()
    
    assert width == 1080  # Default width
    assert height == 1920  # Default height
    assert display_num is None


def test_shell_command(initialized_tool, mock_command_run):
    result = initialized_tool.shell("test command", take_screenshot=False)
    
    assert any(
        'docker exec test_docker_id bash -c \'test command\'' in str(call)
        for call in mock_command_run.call_args_list
    )
    
    assert result.output == "test output"
    assert result.error == "test error"
    assert result.base64_image is None


@patch("time.sleep")
def test_shell_command_with_screenshot(mock_sleep, initialized_tool, mock_command_run):
    with patch.object(initialized_tool, 'screenshot') as mock_screenshot:
        mock_screenshot.return_value.base64_image = "test_base64"
        
        result = initialized_tool.shell("test command", take_screenshot=True)
        
        assert mock_command_run.call_count >= 1
        assert mock_screenshot.call_count >= 1
        mock_sleep.assert_called_once_with(initialized_tool._screenshot_delay)
        
        assert result.output == "test output"
        assert result.error == "test error"
        assert result.base64_image == "test_base64"


@patch("os.path.exists")
@patch("builtins.open")
def test_screenshot_success(mock_open, mock_exists, initialized_tool, mock_command_run):
    mock_exists.return_value = True
    mock_file = MagicMock()
    mock_file.__enter__.return_value.read.return_value = b"test image data"
    mock_open.return_value = mock_file

    result = initialized_tool.screenshot()

    # Check mkdir command
    assert any("mkdir -p /tmp/outputs" in str(call) for call in mock_command_run.call_args_list)
    # Check scrot command
    assert any("scrot -f" in str(call) for call in mock_command_run.call_args_list)
    
    assert result.output == ""
    assert result.base64_image == "dGVzdCBpbWFnZSBkYXRh"  # base64 encoded "test image data"


def test_screenshot_failure(initialized_tool, mock_command_run):
    mock_command_run.return_value = (1, "", "Screenshot failed")

    with pytest.raises(ToolError, match="Failed to take screenshot: Screenshot failed"):
        initialized_tool.screenshot()
