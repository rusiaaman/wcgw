import unittest
from unittest.mock import patch, MagicMock
from wcgw.client.sys_utils import maybe_truncate, command_run, MAX_RESPONSE_LEN, TRUNCATED_MESSAGE
import subprocess
from typing import Tuple


class TestSysUtils(unittest.TestCase):
    def test_maybe_truncate_short_content(self):
        content = "Short content"
        result = maybe_truncate(content)
        self.assertEqual(result, content)

    def test_maybe_truncate_long_content(self):
        content = "x" * (MAX_RESPONSE_LEN + 100)
        result = maybe_truncate(content)
        self.assertEqual(len(result), MAX_RESPONSE_LEN + len(TRUNCATED_MESSAGE))
        self.assertTrue(result.endswith(TRUNCATED_MESSAGE))

    def test_maybe_truncate_custom_length(self):
        content = "Hello World"
        truncate_after = 5
        result = maybe_truncate(content, truncate_after)
        self.assertEqual(result, "Hello" + TRUNCATED_MESSAGE)

    def test_maybe_truncate_none_length(self):
        content = "x" * (MAX_RESPONSE_LEN + 100)
        result = maybe_truncate(content, None)
        self.assertEqual(result, content)

    @patch("subprocess.Popen")
    def test_command_run_success(self, mock_popen):
        # Setup mock
        process_mock = MagicMock()
        process_mock.communicate.return_value = ("stdout", "stderr")
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        # Run command
        returncode, stdout, stderr = command_run("echo test")

        # Verify results
        self.assertEqual(returncode, 0)
        self.assertEqual(stdout, "stdout")
        self.assertEqual(stderr, "stderr")
        mock_popen.assert_called_once_with(
            "echo test",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

    @patch("subprocess.Popen")
    def test_command_run_with_timeout(self, mock_popen):
        process_mock = MagicMock()
        process_mock.communicate.side_effect = subprocess.TimeoutExpired("cmd", 1.0)
        process_mock.kill = MagicMock()
        mock_popen.return_value = process_mock

        with self.assertRaises(TimeoutError):
            command_run("sleep 10", timeout=1.0)

        process_mock.kill.assert_called_once()

    @patch("subprocess.Popen")
    def test_command_run_binary_mode(self, mock_popen):
        process_mock = MagicMock()
        process_mock.communicate.return_value = (b"binary stdout", b"binary stderr")
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        returncode, stdout, stderr = command_run("cat binary_file", text=False)

        self.assertEqual(returncode, 0)
        mock_popen.assert_called_once_with(
            "cat binary_file",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )

    @patch("subprocess.Popen")
    def test_command_run_truncate_output(self, mock_popen):
        # Create long output that should be truncated
        long_output = "x" * (MAX_RESPONSE_LEN + 100)
        
        process_mock = MagicMock()
        process_mock.communicate.return_value = (long_output, "stderr")
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        returncode, stdout, stderr = command_run("some command")

        self.assertEqual(returncode, 0)
        self.assertTrue(stdout.endswith(TRUNCATED_MESSAGE))
        self.assertEqual(len(stdout), MAX_RESPONSE_LEN + len(TRUNCATED_MESSAGE))


if __name__ == "__main__":
    unittest.main()
