import json
import os
import pytest
from pathlib import Path
import tempfile
from wcgw.client.anthropic_client import (
    text_from_editor,
    save_history,
    parse_user_message_special,
)
import rich.console
from unittest.mock import patch, mock_open, MagicMock


@pytest.fixture
def console():
    return rich.console.Console(style="bright_black", highlight=False, markup=False)


def test_text_from_editor_direct_input(console):
    with patch('builtins.input', return_value="Test input"):
        result = text_from_editor(console)
        assert result == "Test input"


def test_text_from_editor_with_editor():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tmp') as tf:
        tf.write("Test content from editor")
        tf.flush()
        
        with patch('builtins.input', return_value=""):
            with patch('os.environ.get', return_value="cat"):  # Use 'cat' as editor for testing
                with patch('subprocess.run') as mock_run:
                    with patch('builtins.open', mock_open(read_data="Test content from editor")):
                        console = rich.console.Console()
                        result = text_from_editor(console)
                        assert result == "Test content from editor"
                        mock_run.assert_called_once()


def test_save_history(tmp_path):
    # Create a temporary directory for testing
    history = [
        {"role": "system", "content": "System message"},
        {"role": "user", "content": "Test message"},
        {"role": "assistant", "content": "Test response"}
    ]
    session_id = "test123"
    
    # Create the .wcgw directory
    wcgw_dir = tmp_path / '.wcgw'
    wcgw_dir.mkdir(parents=True, exist_ok=True)
    
    # Patch Path to return our temp directory
    with patch('pathlib.Path', return_value=wcgw_dir):
        # Create a mock file context
        with patch('builtins.open', mock_open()) as mock_file:
            save_history(history, session_id)
            
            # Verify the file was opened
            mock_file.assert_called_once()
            
            # Get all the written content by joining all write calls
            written_content = ''
            for call_args in mock_file().write.call_args_list:
                written_content += call_args[0][0]
            
            # Verify the content written was valid JSON
            parsed_content = json.loads(written_content)
            assert len(parsed_content) == len(history)
            assert parsed_content == history  # Verify exact content match


def test_parse_user_message_special_text_only():
    msg = "Hello\\nWorld"
    result = parse_user_message_special(msg)
    assert result["role"] == "user"
    assert isinstance(result["content"], list)
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "Hello\\nWorld"


def test_parse_user_message_special_with_image(tmp_path):
    # Create a temporary image file
    image_path = tmp_path / "test.png"
    with open(image_path, "wb") as f:
        f.write(b"fake image data")
    
    msg = f"%image {str(image_path)}\nSome text"
    
    with patch('base64.b64encode', return_value=b"fake_base64"):
        with patch('mimetypes.guess_type', return_value=("image/png", None)):
            result = parse_user_message_special(msg)
            assert result["role"] == "user"
            assert isinstance(result["content"], list)
            assert len(result["content"]) == 2
            assert result["content"][0]["type"] == "image"
            assert result["content"][0]["source"]["type"] == "base64"
            assert result["content"][0]["source"]["media_type"] == "image/png"
            assert result["content"][0]["source"]["data"] == "fake_base64"
            assert result["content"][1]["type"] == "text"
            assert result["content"][1]["text"] == "Some text"