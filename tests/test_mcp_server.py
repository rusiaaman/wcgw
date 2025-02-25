import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp_wcgw.server.models import InitializationOptions
from mcp_wcgw.types import (
    GetPromptResult,
    Prompt,
    PromptMessage,
    TextContent,
)
from mcp_wcgw.types import Tool as ToolParam
from pydantic import ValidationError

from wcgw.client.bash_state.bash_state import CONFIG, BashState
from wcgw.client.mcp_server import server
from wcgw.client.mcp_server.server import (
    Console,
    handle_call_tool,
    handle_get_prompt,
    handle_list_prompts,
    handle_list_resources,
    handle_list_tools,
    handle_read_resource,
    main,
)


# Reset server.BASH_STATE before all tests
@pytest.fixture(scope="function", autouse=True)
def setup_bash_state():
    """Setup BashState for each test"""

    # Update CONFIG immediately
    CONFIG.update(3, 55, 5)

    # Create new BashState with mode
    home_dir = os.path.expanduser("~")
    bash_state = BashState(Console(), home_dir, None, None, None, "wcgw", False, None)
    server.BASH_STATE = bash_state

    try:
        yield server.BASH_STATE
    finally:
        try:
            bash_state.cleanup()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        server.BASH_STATE = None


@pytest.mark.asyncio
async def test_handle_list_resources(setup_bash_state):
    resources = await handle_list_resources()
    assert isinstance(resources, list)
    assert len(resources) == 0


@pytest.mark.asyncio
async def test_handle_read_resource(setup_bash_state):
    with pytest.raises(ValueError, match="No resources available"):
        await handle_read_resource("http://example.com")


@pytest.mark.asyncio
async def test_handle_list_prompts(setup_bash_state):
    prompts = await handle_list_prompts()
    assert isinstance(prompts, list)
    assert len(prompts) > 0
    assert isinstance(prompts[0], Prompt)
    assert "KnowledgeTransfer" in [p.name for p in prompts]
    # Test prompt structure
    kt_prompt = next(p for p in prompts if p.name == "KnowledgeTransfer")
    assert (
        kt_prompt.description
        == "Prompt for invoking ContextSave tool in order to do a comprehensive knowledge transfer of a coding task. Prompts to save detailed error log and instructions."
    )


@pytest.mark.asyncio
async def test_handle_get_prompt(setup_bash_state):
    # Test valid prompt
    result = await handle_get_prompt("KnowledgeTransfer", None)
    assert isinstance(result, GetPromptResult)
    assert len(result.messages) == 1
    assert isinstance(result.messages[0], PromptMessage)
    assert result.messages[0].role == "user"
    assert isinstance(result.messages[0].content, TextContent)

    # Test invalid prompt
    with pytest.raises(KeyError):
        await handle_get_prompt("NonExistentPrompt", None)

    # Test with arguments
    result = await handle_get_prompt("KnowledgeTransfer", {"arg": "value"})
    assert isinstance(result, GetPromptResult)


@pytest.mark.asyncio
async def test_handle_list_tools():
    print("Running test_handle_list_tools")
    tools = await handle_list_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0

    # Check all required tools are present
    tool_names = {tool.name for tool in tools}
    required_tools = {
        "Initialize",
        "BashCommand",
        "ReadFiles",
        "WriteIfEmpty",
        "ReadImage",
        "FileEdit",
        "ContextSave",
    }
    assert required_tools.issubset(
        tool_names
    ), f"Missing tools: {required_tools - tool_names}"

    # Test each tool's schema and description
    for tool in tools:
        assert isinstance(tool, ToolParam)
        assert tool.inputSchema is not None
        assert isinstance(tool.description, str)
        assert len(tool.description.strip()) > 0

        # Test specific tool properties based on tool type
        if tool.name == "Initialize":
            properties = tool.inputSchema["properties"]
            assert "mode_name" in properties
            assert properties["mode_name"]["enum"] == [
                "wcgw",
                "architect",
                "code_writer",
            ]
            assert "any_workspace_path" in properties
            assert properties["any_workspace_path"]["type"] == "string"
            assert "initial_files_to_read" in properties
            assert properties["initial_files_to_read"]["type"] == "array"
        elif tool.name == "BashCommand":
            properties = tool.inputSchema["properties"]
            assert "action_json" in properties
            assert "wait_for_seconds" in properties
            # Check type field has all the command types
            type_properties = properties["action_json"]["anyOf"]
            type_refs = set(p["$ref"].split("/")[-1] for p in type_properties)
            required_types = {
                "Command",
                "StatusCheck",
                "SendText",
                "SendSpecials",
                "SendAscii",
            }
            assert required_types.issubset(type_refs)
        elif tool.name == "FileEdit":
            properties = tool.inputSchema["properties"]
            assert "file_path" in properties
            assert "file_edit_using_search_replace_blocks" in properties


@pytest.mark.asyncio
async def test_handle_call_tool(setup_bash_state):
    # Test missing arguments
    with pytest.raises(ValueError, match="Missing arguments"):
        await handle_call_tool("Initialize", None)

    # Test Initialize tool with valid arguments
    init_args = {
        "any_workspace_path": "",
        "initial_files_to_read": [],
        "task_id_to_resume": "",
        "mode_name": "wcgw",
        "type": "first_call",
    }
    result = await handle_call_tool("Initialize", init_args)
    assert isinstance(result, list)
    assert len(result) > 0
    assert isinstance(result[0], TextContent)
    assert "Initialize" in result[0].text

    # Test JSON string argument handling
    json_args = {"action_json": {"command": "ls"}, "wait_for_seconds": None}
    result = await handle_call_tool("BashCommand", json_args)
    assert isinstance(result, list)

    # Test validation error handling
    with pytest.raises(ValidationError):
        invalid_args = {
            "any_workspace_path": 123,  # Invalid type
            "initial_files_to_read": [],
            "task_id_to_resume": "",
            "mode_name": "wcgw",
        }
        await handle_call_tool("Initialize", invalid_args)

    # Test tool exception handling
    with patch(
        "wcgw.client.mcp_server.server.get_tool_output",
        side_effect=Exception("Test error"),
    ):
        result = await handle_call_tool(
            "BashCommand", {"action_json": {"command": "ls"}, "wait_for_seconds": None}
        )
        assert "GOT EXCEPTION" in result[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_image_response(setup_bash_state):
    # Test handling of image content
    mock_image_data = "fake_image_data"
    mock_media_type = "image/png"

    # Create a mock image object that matches the expected response
    mock_image = Mock()
    mock_image.data = mock_image_data
    mock_image.media_type = mock_media_type

    with patch(
        "wcgw.client.mcp_server.server.get_tool_output",
        return_value=([mock_image], None),
    ):
        result = await handle_call_tool("ReadImage", {"file_path": "test.png"})
        assert result[0].data == mock_image_data
        assert result[0].mimeType == mock_media_type


@pytest.mark.asyncio
async def test_main(setup_bash_state):
    CONFIG.update(3, 55, 5)  # Ensure CONFIG is set before main()
    # Mock the version function
    with patch("importlib.metadata.version", return_value="1.0.0") as mock_version:
        # Mock the stdio server
        mock_read_stream = AsyncMock()
        mock_write_stream = AsyncMock()
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = (mock_read_stream, mock_write_stream)

        with patch("mcp_wcgw.server.stdio.stdio_server", return_value=mock_context):
            # Mock server.run to prevent actual server start
            with patch("wcgw.client.mcp_server.server.server.run") as mock_run:
                await main()

                # Verify CONFIG update
                assert CONFIG.timeout == 3
                assert CONFIG.timeout_while_output == 55
                assert CONFIG.output_wait_patience == 5

                # Verify server run was called with correct initialization
                mock_run.assert_called_once()
                init_options = mock_run.call_args[0][2]
                assert isinstance(init_options, InitializationOptions)
                assert init_options.server_name == "wcgw"
                assert init_options.server_version == "1.0.0"
