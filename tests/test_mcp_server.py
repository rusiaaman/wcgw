import asyncio
import os
import re
import threading
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.server.models import InitializationOptions
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptMessage,
    TextContent,
)
from mcp.types import Tool as ToolParam
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
    server.BASH_STATES.clear()
    server.STATE_CALL_LOCKS.clear()
    server.STATE_CREATION_LOCKS.clear()
    server.BASH_STATE = bash_state
    server.BASH_STATES[bash_state.current_thread_id] = bash_state

    try:
        yield server.BASH_STATE
    finally:
        states = {
            id(state): state
            for state in [bash_state, server.BASH_STATE, *server.BASH_STATES.values()]
            if state is not None
        }
        for state in states.values():
            try:
                state.cleanup()
            except Exception as e:
                print(f"Error during cleanup: {e}")
        server.BASH_STATES.clear()
        server.STATE_CALL_LOCKS.clear()
        server.STATE_CREATION_LOCKS.clear()
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
        "ReadImage",
        "FileWriteOrEdit",
        "ContextSave",
    }
    assert required_tools.issubset(tool_names), (
        f"Missing tools: {required_tools - tool_names}"
    )

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
            # BashCommand schema is flattened, so it has the action fields directly
            assert "type" in properties
            assert "command" in properties
            assert "wait_for_seconds" in properties
            assert "thread_id" in properties
            # Check type field has all the command types
            type_refs = set(properties)
            required_types = {
                "command",
                "status_check",
                "send_text",
                "send_specials",
                "send_ascii",
            }
            assert required_types.issubset(type_refs)
        elif tool.name in {"ReadFiles", "ReadImage", "ContextSave"}:
            properties = tool.inputSchema["properties"]
            assert "thread_id" in properties
            assert "thread_id" not in tool.inputSchema.get("required", [])
        elif tool.name == "FileWriteOrEdit":
            properties = tool.inputSchema["properties"]
            assert "file_path" in properties
            assert "text_or_search_replace_blocks" in properties


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
        "thread_id": "",
    }
    result = await handle_call_tool("Initialize", init_args)
    assert isinstance(result, list)
    assert len(result) > 0
    assert isinstance(result[0], TextContent)
    assert "Initialize" in result[0].text
    initialized_thread = re.search(r"Use thread_id=(\w+)", result[0].text)
    assert initialized_thread is not None

    # Test JSON string argument handling
    json_args = {
        "action_json": {
            "command": "ls",
            "thread_id": initialized_thread.group(1),
        },
    }
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
            "BashCommand",
            {
                "action_json": {
                    "command": "ls",
                    "thread_id": initialized_thread.group(1),
                },
            },
        )
        assert "GOT EXCEPTION" in result[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_preserves_shells_across_thread_ids(
    setup_bash_state, tmp_path
):
    first_workspace = tmp_path / "first"
    second_workspace = tmp_path / "second"
    first_workspace.mkdir()
    second_workspace.mkdir()

    init_args = {
        "initial_files_to_read": [],
        "task_id_to_resume": "",
        "mode_name": "wcgw",
        "type": "first_call",
        "thread_id": "",
    }
    first_init = await handle_call_tool(
        "Initialize", {**init_args, "any_workspace_path": str(first_workspace)}
    )
    first_match = re.search(r"Use thread_id=(\w+)", first_init[0].text)
    assert first_match is not None
    first_thread_id = first_match.group(1)

    pending = await handle_call_tool(
        "BashCommand",
        {
            "type": "command",
            "command": "sleep 10",
            "thread_id": first_thread_id,
            "wait_for_seconds": 0.1,
        },
    )
    assert "status = still running" in pending[0].text

    second_init = await handle_call_tool(
        "Initialize", {**init_args, "any_workspace_path": str(second_workspace)}
    )
    second_match = re.search(r"Use thread_id=(\w+)", second_init[0].text)
    assert second_match is not None
    second_thread_id = second_match.group(1)
    assert second_thread_id != first_thread_id

    second_pwd = await handle_call_tool(
        "BashCommand",
        {
            "type": "command",
            "command": "pwd",
            "thread_id": second_thread_id,
            "wait_for_seconds": 0.5,
        },
    )
    assert str(second_workspace) in second_pwd[0].text

    first_status = await handle_call_tool(
        "BashCommand",
        {
            "type": "status_check",
            "status_check": True,
            "thread_id": first_thread_id,
            "wait_for_seconds": 0.1,
        },
    )
    assert "status = still running" in first_status[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_runs_different_shell_states_concurrently(
    setup_bash_state,
):
    first_state = server.new_state("thread_a")
    second_state = server.new_state("thread_b")
    server.BASH_STATES["thread_a"] = first_state
    server.BASH_STATES["thread_b"] = second_state
    call_order: list[str] = []

    def fake_get_tool_output(*args, **kwargs):
        tool_call = args[1]
        thread_id = tool_call.action_json.thread_id
        call_order.append(f"{thread_id}:start")
        if thread_id == "thread_a":
            time.sleep(0.2)
        call_order.append(f"{thread_id}:end")
        return ["ok"], 0.0

    with patch(
        "wcgw.client.mcp_server.server.get_tool_output",
        side_effect=fake_get_tool_output,
    ):
        first_call = asyncio.create_task(
            handle_call_tool(
                "BashCommand",
                {"type": "command", "command": "first", "thread_id": "thread_a"},
            )
        )
        await asyncio.sleep(0.02)
        second_call = asyncio.create_task(
            handle_call_tool(
                "BashCommand",
                {"type": "command", "command": "second", "thread_id": "thread_b"},
            )
        )
        await asyncio.gather(first_call, second_call)

    assert call_order.index("thread_b:end") < call_order.index("thread_a:end")


@pytest.mark.asyncio
async def test_handle_call_tool_serializes_calls_for_same_thread_id(
    setup_bash_state,
):
    state = server.new_state("thread_a")
    server.BASH_STATES["thread_a"] = state
    counter_lock = threading.Lock()
    active_calls = 0
    max_active_calls = 0

    def fake_get_tool_output(*args, **kwargs):
        nonlocal active_calls, max_active_calls
        with counter_lock:
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        time.sleep(0.05)
        with counter_lock:
            active_calls -= 1
        return ["ok"], 0.0

    with patch(
        "wcgw.client.mcp_server.server.get_tool_output",
        side_effect=fake_get_tool_output,
    ):
        await asyncio.gather(
            handle_call_tool(
                "BashCommand",
                {"type": "command", "command": "first", "thread_id": "thread_a"},
            ),
            handle_call_tool(
                "BashCommand",
                {"type": "command", "command": "second", "thread_id": "thread_a"},
            ),
        )

    assert max_active_calls == 1


@pytest.mark.asyncio
async def test_first_call_state_creation_does_not_block_event_loop(setup_bash_state):
    assert server.BASH_STATE is not None
    created_state = server.BASH_STATE

    def slow_new_state(thread_id):
        time.sleep(0.2)
        return created_state

    with (
        patch("wcgw.client.mcp_server.server.new_state", side_effect=slow_new_state),
        patch(
            "wcgw.client.mcp_server.server.get_tool_output",
            return_value=(["ok"], 0.0),
        ),
    ):
        call = asyncio.create_task(
            handle_call_tool(
                "Initialize",
                {
                    "any_workspace_path": "",
                    "initial_files_to_read": [],
                    "task_id_to_resume": "",
                    "mode_name": "wcgw",
                    "type": "first_call",
                    "thread_id": "",
                },
            )
        )
        started = time.monotonic()
        await asyncio.sleep(0.02)
        elapsed = time.monotonic() - started
        assert elapsed < 0.1
        await call


@pytest.mark.asyncio
async def test_restore_is_atomic_for_same_thread_id(setup_bash_state):
    restored_state = server.new_state("restored")
    server.BASH_STATES.pop("restored", None)
    restore_calls = 0
    restore_lock = threading.Lock()

    def slow_restore(thread_id):
        nonlocal restore_calls
        with restore_lock:
            restore_calls += 1
        time.sleep(0.1)
        return restored_state

    with (
        patch("wcgw.client.mcp_server.server.restored_state", side_effect=slow_restore),
        patch(
            "wcgw.client.mcp_server.server.get_tool_output",
            return_value=(["ok"], 0.0),
        ),
    ):
        await asyncio.gather(
            handle_call_tool(
                "BashCommand",
                {"type": "command", "command": "first", "thread_id": "restored"},
            ),
            handle_call_tool(
                "BashCommand",
                {"type": "command", "command": "second", "thread_id": "restored"},
            ),
        )

    assert restore_calls == 1


@pytest.mark.asyncio
async def test_handle_call_tool_routes_read_tools_by_thread_id(setup_bash_state):
    first_state = server.new_state("thread_a")
    second_state = server.new_state("thread_b")
    server.BASH_STATES["thread_a"] = first_state
    server.BASH_STATES["thread_b"] = second_state

    def fake_get_tool_output(*args, **kwargs):
        context = args[0]
        return [context.bash_state.current_thread_id], 0.0

    with patch(
        "wcgw.client.mcp_server.server.get_tool_output",
        side_effect=fake_get_tool_output,
    ):
        result = await handle_call_tool(
            "ReadFiles",
            {"file_paths": ["/tmp/example"], "thread_id": "thread_b"},
        )

    assert result[0].text == "thread_b"


@pytest.mark.asyncio
async def test_legacy_read_authorizes_later_threaded_write(setup_bash_state, tmp_path):
    second_state = server.new_state("thread_b")
    server.BASH_STATES["thread_b"] = second_state
    test_file = tmp_path / "legacy.txt"
    test_file.write_text("legacy")

    read_result = await handle_call_tool(
        "ReadFiles", {"file_paths": [str(test_file)]}
    )
    assert "legacy" in read_result[0].text
    assert server.BASH_STATE is not None
    assert str(test_file) in server.BASH_STATE.whitelist_for_overwrite
    assert str(test_file) not in second_state.whitelist_for_overwrite

    def inspect_write_state(*args, **kwargs):
        context = args[0]
        authorized = str(test_file) in context.bash_state.whitelist_for_overwrite
        return [str(authorized)], 0.0

    with patch(
        "wcgw.client.mcp_server.server.get_tool_output",
        side_effect=inspect_write_state,
    ):
        write_result = await handle_call_tool(
            "FileWriteOrEdit",
            {
                "file_path": str(test_file),
                "percentage_to_change": 100,
                "text_or_search_replace_blocks": "replacement",
                "thread_id": "thread_b",
            },
        )

    assert write_result[0].text == "True"


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
        assert server.BASH_STATE is not None
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

        with patch("mcp.server.stdio.stdio_server", return_value=mock_context):
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
