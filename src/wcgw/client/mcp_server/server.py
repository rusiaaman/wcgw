import importlib
import logging
import os
from typing import Any

import mcp_wcgw.server.stdio
import mcp_wcgw.types as types
from mcp_wcgw.server import NotificationOptions, Server
from mcp_wcgw.server.models import InitializationOptions
from mcp_wcgw.types import Tool as ToolParam
from pydantic import AnyUrl

from wcgw.client.modes import KTS
from wcgw.client.tool_prompts import TOOL_PROMPTS

from ...types_ import (
    Initialize,
)
from ..bash_state.bash_state import CONFIG, BashState
from ..tools import (
    Context,
    default_enc,
    get_tool_output,
    parse_tool_by_name,
    which_tool_name,
)

server = Server("wcgw")

# Log only time stamp
logging.basicConfig(level=logging.INFO, format="%(asctime)s: %(message)s")
logger = logging.getLogger("wcgw")


class Console:
    def print(self, msg: str, *args: Any, **kwargs: Any) -> None:
        logger.info(msg)

    def log(self, msg: str, *args: Any, **kwargs: Any) -> None:
        logger.info(msg)


@server.list_resources()  # type: ignore
async def handle_list_resources() -> list[types.Resource]:
    return []


@server.read_resource()  # type: ignore
async def handle_read_resource(uri: AnyUrl) -> str:
    raise ValueError("No resources available")


PROMPTS = {
    "KnowledgeTransfer": (
        types.Prompt(
            name="KnowledgeTransfer",
            description="Prompt for invoking ContextSave tool in order to do a comprehensive knowledge transfer of a coding task. Prompts to save detailed error log and instructions.",
        ),
        KTS,
    )
}


@server.list_prompts()  # type: ignore
async def handle_list_prompts() -> list[types.Prompt]:
    return [x[0] for x in PROMPTS.values()]


@server.get_prompt()  # type: ignore
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    assert BASH_STATE
    messages = [
        types.PromptMessage(
            role="user",
            content=types.TextContent(
                type="text", text=PROMPTS[name][1][BASH_STATE.mode]
            ),
        )
    ]
    return types.GetPromptResult(messages=messages)


@server.list_tools()  # type: ignore
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """

    tools_ = [
        ToolParam(
            inputSchema=tool.inputSchema,
            name=tool.name,
            description=tool.description,
        )
        for tool in TOOL_PROMPTS
    ]
    return tools_


@server.call_tool()  # type: ignore
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    global BASH_STATE
    if not arguments:
        raise ValueError("Missing arguments")

    tool_type = which_tool_name(name)
    tool_call = parse_tool_by_name(name, arguments)

    try:
        assert BASH_STATE
        output_or_dones, _ = get_tool_output(
            Context(BASH_STATE, BASH_STATE.console),
            tool_call,
            default_enc,
            0.0,
            lambda x, y: ("", 0),
            8000,
        )

    except Exception as e:
        output_or_dones = [f"GOT EXCEPTION while calling tool. Error: {e}"]

    content: list[types.TextContent | types.ImageContent | types.EmbeddedResource] = []
    for output_or_done in output_or_dones:
        if isinstance(output_or_done, str):
            if issubclass(tool_type, Initialize):
                output_or_done += """
- Additional important note: as soon as you encounter "The user has chosen to disallow the tool call.", immediately stop doing everything and ask user for the reason.

Initialize call done.
    """

            content.append(types.TextContent(type="text", text=output_or_done))
        else:
            content.append(
                types.ImageContent(
                    type="image",
                    data=output_or_done.data,
                    mimeType=output_or_done.media_type,
                )
            )

    return content


BASH_STATE = None


async def main() -> None:
    global BASH_STATE
    CONFIG.update(3, 55, 5)
    version = str(importlib.metadata.version("wcgw"))
    home_dir = os.path.expanduser("~")
    with BashState(
        Console(), home_dir, None, None, None, None, True, None
    ) as BASH_STATE:
        BASH_STATE.console.log("wcgw version: " + version)
        # Run the server using stdin/stdout streams
        async with mcp_wcgw.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="wcgw",
                    server_version=version,
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
                raise_exceptions=False,
            )
