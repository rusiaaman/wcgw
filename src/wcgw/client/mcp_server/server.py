import importlib
import json
import logging
import os
from typing import Any

import mcp_wcgw.server.stdio
import mcp_wcgw.types as types
from mcp_wcgw.server import NotificationOptions, Server
from mcp_wcgw.server.models import InitializationOptions
from mcp_wcgw.types import Tool as ToolParam
from pydantic import AnyUrl, ValidationError

from wcgw.client.modes import KTS

from ...types_ import (
    BashCommand,
    BashInteraction,
    ContextSave,
    FileEdit,
    Initialize,
    ReadFiles,
    ReadImage,
    ResetShell,
    WriteIfEmpty,
)
from ..bash_state.bash_state import CONFIG, BashState
from ..tools import Context, default_enc, get_tool_output, which_tool_name

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

    with open(
        os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "diff-instructions.txt"
        )
    ) as f:
        diffinstructions = f.read()

    tools_ = [
        ToolParam(
            inputSchema=Initialize.model_json_schema(),
            name="Initialize",
            description="""
- Always call this at the start of the conversation before using any of the shell tools from wcgw.
- This will reset the shell.
- Use `any_workspace_path` to initialize the shell in the appropriate project directory.
- If the user has mentioned a workspace or project root, use it to set `any_workspace_path`.
- If the user has mentioned a folder or file with unclear project root, use the file or folder as `any_workspace_path`.
- If user has mentioned any files use `initial_files_to_read` to read, use absolute paths only.
- If `any_workspace_path` is provided, a tree structure of the workspace will be shown.
- Leave `any_workspace_path` as empty if no file or folder is mentioned.
- By default use mode "wcgw"
- In "code-writer" mode, set the commands and globs which user asked to set, otherwise use 'all'.
- In order to change the mode later, call this tool again but be sure to not provide any other argument like task_id_to_resume unnecessarily.
""",
        ),
        ToolParam(
            inputSchema=BashCommand.model_json_schema(),
            name="BashCommand",
            description=f"""
- Execute a bash command. This is stateful (beware with subsequent calls).
- Do not use interactive commands like nano. Prefer writing simpler commands.
- Status of the command and the current working directory will always be returned at the end.
- Optionally `exit shell has restarted` is the output, in which case environment resets, you can run fresh commands.
- The first or the last line might be `(...truncated)` if the output is too long.
- Always run `pwd` if you get any file or directory not found error to make sure you're not lost.
- The control will return to you in {CONFIG.timeout} seconds regardless of the status. For heavy commands, keep checking status using BashInteraction till they are finished.
- Run long running commands in background using screen instead of "&".
- Use longer wait_for_seconds if the command is expected to run for a long time.
- Do not use 'cat' to read files, use ReadFiles tool instead.
""",
        ),
        ToolParam(
            inputSchema=BashInteraction.model_json_schema(),
            name="BashInteraction",
            description="""
- Interact with running program using this tool
- Special keys like arrows, interrupts, enter, etc.
- Send text input to the running program.
- Send send_specials=["Enter"] to recheck status of a running program.
- Only one of send_text, send_specials, send_ascii should be provided.
- This returns within 5 seconds, for heavy programs keep checking status for upto 10 turns before asking user to continue checking again.
- Programs don't hang easily, so most likely explanation for no output is usually that the program is still running, and you need to check status again using ["Enter"].
- Do not send Ctrl-c before checking for status till 10 minutes or whatever is appropriate for the program to finish.
- Set longer wait_for_seconds when program is expected to run for a long time.
""",
        ),
        ToolParam(
            inputSchema=ReadFiles.model_json_schema(),
            name="ReadFiles",
            description="""
- Read full file content of one or more files.
- Provide absolute file paths only
""",
        ),
        ToolParam(
            inputSchema=WriteIfEmpty.model_json_schema(),
            name="WriteIfEmpty",
            description="""
- Write content to an empty or non-existent file. Provide file path and content. Use this instead of BashCommand for writing new files.
- Provide absolute file path only.
- For editing existing files, use FileEdit instead of this tool.
""",
        ),
        ToolParam(
            inputSchema=ReadImage.model_json_schema(),
            name="ReadImage",
            description="Read an image from the shell.",
        ),
        ToolParam(
            inputSchema=ResetShell.model_json_schema(),
            name="ResetShell",
            description="Resets the shell. Use only if all interrupts and prompt reset attempts have failed repeatedly.",
        ),
        ToolParam(
            inputSchema=FileEdit.model_json_schema(),
            name="FileEdit",
            description="""
- Use absolute file path only.
- Use SEARCH/REPLACE blocks to edit the file.
- If the edit fails due to block not matching, please retry with correct block till it matches. Re-read the file to ensure you've all the lines correct.
"""
            + diffinstructions,
        ),
        ToolParam(
            inputSchema=ContextSave.model_json_schema(),
            name="ContextSave",
            description="""
Saves provided description and file contents of all the relevant file paths or globs in a single text file.
- Provide random unqiue id or whatever user provided.
- Leave project path as empty string if no project path""",
        ),
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

    try:
        tool_call = tool_type(**arguments)
    except ValidationError:

        def try_json(x: str) -> Any:
            if not isinstance(x, str):
                return x
            try:
                return json.loads(x)
            except json.JSONDecodeError:
                return x

        tool_call = tool_type(**{k: try_json(v) for k, v in arguments.items()})

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
    BASH_STATE = BashState(Console(), home_dir, None, None, None, None, None)
    try:
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
    finally:
        BASH_STATE.cleanup()
