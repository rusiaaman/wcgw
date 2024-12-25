import unittest
from unittest.mock import patch, MagicMock
from wcgw.client.computer_use import (
    ComputerTool,
    ToolResult,
    ToolError,
    ScalingSource,
    chunks,
)
import time


class TestComputerUse(unittest.TestCase):
    def setUp(self):
        self.computer = ComputerTool()
        self.computer.width = 1920
        self.computer.height = 1080
        self.computer.display_num = 0
        self.computer.docker_image_id = "test_docker_id"
        self.computer._display_prefix = "DISPLAY=:0 "
        self.computer.xdotool = "DISPLAY=:0 xdotool"

    def test_tool_result_operations(self):
        # Test ToolResult creation and combination
        result1 = ToolResult(output="test1", error=None, base64_image=None)
        result2 = ToolResult(output="test2", error="error2", base64_image=None)
        
        # Test addition
        combined = result1 + result2
        self.assertEqual(combined.output, "test1test2")
        self.assertEqual(combined.error, "error2")
        self.assertIsNone(combined.base64_image)

        # Test bool evaluation
        self.assertTrue(bool(result1))
        self.assertFalse(bool(ToolResult()))

    def test_chunks_function(self):
        # Test the chunks utility function
        text = "123456789"
        result = chunks(text, 3)
        self.assertEqual(result, ["123", "456", "789"])
        
        # Test with uneven chunks
        result = chunks(text, 4)
        self.assertEqual(result, ["1234", "5678", "9"])

    @patch("wcgw.client.computer_use.command_run")
    def test_get_screen_info(self, mock_command_run):
        # Mock the shell command output
        mock_command_run.return_value = (0, "1920,1080,0", "")
        
        width, height, display_num = self.computer.get_screen_info()
        
        self.assertEqual(width, 1920)
        self.assertEqual(height, 1080)
        self.assertEqual(display_num, 0)
        self.assertEqual(self.computer._display_prefix, "DISPLAY=:0 ")

    @patch("wcgw.client.computer_use.command_run")
    @patch("os.path.exists")
    @patch("builtins.open")
    def test_mouse_move_action(self, mock_open, mock_exists, mock_command_run):
        mock_command_run.return_value = (0, "", "")
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = b"test_image"
        
        # Test simple mouse move
        result = self.computer(action="mouse_move", coordinate=(100, 100))
        self.assertEqual(result.error, "")
        
        # Test mouse move with click
        result = self.computer(
            action="mouse_move",
            coordinate=(100, 100),
            do_left_click_on_move=True
        )
        self.assertEqual(result.error, "")

    @patch("wcgw.client.computer_use.command_run")
    @patch("os.path.exists")
    @patch("builtins.open")
    def test_typing_actions(self, mock_open, mock_exists, mock_command_run):
        mock_command_run.return_value = (0, "", "")
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = b"test_image"
        
        # Test key action
        result = self.computer(action="key", text="Return")
        self.assertEqual(result.error, "")
        
        # Test type action
        text = "Hello\nWorld"
        result = self.computer(action="type", text=text)
        self.assertEqual(result.error, "")

    def test_invalid_inputs(self):
        # Test invalid action
        with self.assertRaises(ToolError):
            self.computer(action="invalid_action")
        
        # Test missing coordinate for mouse move
        with self.assertRaises(ToolError):
            self.computer(action="mouse_move")
        
        # Test invalid coordinate type
        with self.assertRaises(ToolError):
            self.computer(action="mouse_move", coordinate="invalid")

    def test_scaling_coordinates(self):
        # Test API to computer scaling
        x, y = self.computer.scale_coordinates(ScalingSource.API, 800, 600)
        self.assertTrue(isinstance(x, int))
        self.assertTrue(isinstance(y, int))
        
        # Test computer to API scaling
        x, y = self.computer.scale_coordinates(ScalingSource.COMPUTER, 1920, 1080)
        self.assertTrue(isinstance(x, int))
        self.assertTrue(isinstance(y, int))
        
        # Test out of bounds coordinates
        with self.assertRaises(ToolError):
            self.computer.scale_coordinates(ScalingSource.API, 2000, 2000)

    @patch("wcgw.client.computer_use.command_run")
    @patch("os.path.exists")
    @patch("builtins.open")
    def test_screenshot_functionality(self, mock_open, mock_exists, mock_command_run):
        # Configure mocks
        mock_command_run.return_value = (0, "", "")
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = b"test_image_data"
        mock_open.return_value.__exit__ = MagicMock()
        
        # Test screenshot
        result = self.computer.screenshot()
        self.assertIsNotNone(result.base64_image)
        self.assertEqual(result.error, "")


if __name__ == "__main__":
    unittest.main()
