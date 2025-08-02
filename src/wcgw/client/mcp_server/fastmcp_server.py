import importlib
import logging
import os
from typing import Any, Optional, Union
from pathlib import Path

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

from wcgw.client.modes import KTS
from wcgw.client.tool_prompts import TOOL_PROMPTS

from ...types_ import (
    Initialize,
    BashCommand,
    ReadFiles,
    ReadImage,
    FileWriteOrEdit,
    ContextSave,
)
from ..bash_state.bash_state import CONFIG, BashState, get_tmpdir
from ..tools import (
    Context as WCGWContext,
    ImageData,
    default_enc,
    get_tool_output,
    parse_tool_by_name,
    which_tool_name,
)


# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s: %(message)s")
logger = logging.getLogger("wcgw")


class Console:
    def print(self, msg: str, *args: Any, **kwargs: Any) -> None:
        logger.info(msg)

    def log(self, msg: str, *args: Any, **kwargs: Any) -> None:
        logger.info(msg)


# Global state (single client assumption)
BASH_STATE: Optional[BashState] = None
CUSTOM_INSTRUCTIONS: Optional[str] = None


# Lifecycle context manager
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan():
    global BASH_STATE, CUSTOM_INSTRUCTIONS
    
    # Startup
    CONFIG.update(3, 55, 5)
    version = str(importlib.metadata.version("wcgw"))
    
    # Read custom instructions from environment variable
    CUSTOM_INSTRUCTIONS = os.getenv("WCGW_SERVER_INSTRUCTIONS")
    
    # starting_dir is inside tmp dir
    tmp_dir = get_tmpdir()
    starting_dir = os.path.join(tmp_dir, "claude_playground")
    
    # Create global BashState
    BASH_STATE = BashState(
        Console(), starting_dir, None, None, None, None, True, None
    )
    BASH_STATE.__enter__()
    
    logger.info(f"wcgw version: {version}")
    
    yield
    
    # Shutdown
    if BASH_STATE:
        BASH_STATE.__exit__(None, None, None)
        BASH_STATE = None


# Create FastMCP server
mcp = FastMCP(
    name="wcgw",
    instructions="Shell and coding agent for Claude and other MCP clients",
    lifespan=lifespan
)


# Tool 1: Initialize
@mcp.tool
async def initialize(
    any_workspace_path: str = Field(default="", description="Path to workspace"),
    initial_files_to_read: list[str] = Field(default_factory=list, description="Files to read initially"),
    task_id_to_resume: str = Field(default="", description="Task ID to resume"),
    mode_name: str = Field(default="wcgw", description="Mode name", pattern="^(wcgw|architect|code_writer)$"),
    type: str = Field(default="first_call", description="Initialization type"),
    thread_id: str = Field(default="", description="Thread ID"),
    lint_commands: Union[str, list[str]] = Field(default="all", description="Lint commands"),
    type_check_commands: Union[str, list[str]] = Field(default="all", description="Type check commands"),
    test_commands: Union[str, list[str]] = Field(default="all", description="Test commands"),
    ctx: Context = None
) -> str:
    """
    Always call this at the start of the conversation before using any of the shell tools from wcgw.
    - Use `any_workspace_path` to initialize the shell in the appropriate project directory.
    - If the user has mentioned a workspace or project root or any other file or folder use it to set `any_workspace_path`.
    - If user has mentioned any files use `initial_files_to_read` to read, use absolute paths only (~ allowed)
    - By default use mode "wcgw"
    - In "code-writer" mode, set the commands and globs which user asked to set, otherwise use 'all'.
    - Use type="first_call" if it's the first call to this tool.
    - Use type="user_asked_mode_change" if in a conversation user has asked to change mode.
    - Use type="reset_shell" if in a conversation shell is not working after multiple tries.
    - Use type="user_asked_change_workspace" if in a conversation user asked to change workspace
    """
    global BASH_STATE
    
    # Create Initialize object
    init_obj = Initialize(
        any_workspace_path=any_workspace_path,
        initial_files_to_read=initial_files_to_read,
        task_id_to_resume=task_id_to_resume,
        mode_name=mode_name,
        type=type,
        thread_id=thread_id,
        lint_commands=lint_commands,
        type_check_commands=type_check_commands,
        test_commands=test_commands
    )
    
    # Call the tool
    assert BASH_STATE
    output_or_dones, _ = get_tool_output(
        WCGWContext(BASH_STATE, BASH_STATE.console),
        init_obj,
        default_enc,
        0.0,
        lambda x, y: ("", 0),
        24000,  # coding_max_tokens
        8000,   # noncoding_max_tokens
    )
    
    # Process output
    result = ""
    for output_or_done in output_or_dones:
        if isinstance(output_or_done, str):
            result += output_or_done
    
    # Add custom instructions and additional note
    original_message = """
- Additional important note: as soon as you encounter "The user has chosen to disallow the tool call.", immediately stop doing everything and ask user for the reason.

Initialize call done.
    """
    
    if CUSTOM_INSTRUCTIONS:
        result += f"\n{CUSTOM_INSTRUCTIONS}\n{original_message}"
    else:
        result += original_message
    
    return result


# Tool 2: BashCommand
@mcp.tool
async def bash_command(
    action_json: dict[str, Any] = Field(..., description="Command action"),
    wait_for_seconds: Optional[float] = Field(None, description="Seconds to wait"),
    thread_id: str = Field(default="", description="Thread ID"),
    ctx: Context = None
) -> str:
    """
    Execute a bash command. This is stateful (beware with subsequent calls).
    - Status of the command and the current working directory will always be returned at the end.
    - The first or the last line might be `(...truncated)` if the output is too long.
    - Always run `pwd` if you get any file or directory not found error to make sure you're not lost.
    - Run long running commands in background using screen instead of "&".
    - Do not use 'cat' to read files, use ReadFiles tool instead
    - In order to check status of previous command, use `status_check` with empty command argument.
    - Only command is allowed to run at a time. You need to wait for any previous command to finish before running a new one.
    - Programs don't hang easily, so most likely explanation for no output is usually that the program is still running, and you need to check status again.
    - Do not send Ctrl-c before checking for status till 10 minutes or whatever is appropriate for the program to finish.
    """
    global BASH_STATE
    
    # Create BashCommand object
    bash_cmd = BashCommand(
        action_json=action_json,
        wait_for_seconds=wait_for_seconds,
        thread_id=thread_id
    )
    
    # Call the tool
    assert BASH_STATE
    output_or_dones, _ = get_tool_output(
        WCGWContext(BASH_STATE, BASH_STATE.console),
        bash_cmd,
        default_enc,
        0.0,
        lambda x, y: ("", 0),
        24000,  # coding_max_tokens
        8000,   # noncoding_max_tokens
    )
    
    # Process output
    result = ""
    for output_or_done in output_or_dones:
        if isinstance(output_or_done, str):
            result += output_or_done
            # Stream output to client via logging
            if ctx:
                await ctx.info(output_or_done)
    
    return result


# Tool 3: ReadFiles
@mcp.tool
async def read_files(
    file_paths: list[str] = Field(..., description="File paths to read"),
    thread_id: str = Field(default="", description="Thread ID"),
    ctx: Context = None
) -> str:
    """
    Read full file content of one or more files.
    - Provide absolute paths only (~ allowed)
    - Only if the task requires line numbers understanding:
        - You may extract a range of lines. E.g., `/path/to/file:1-10` for lines 1-10. You can drop start or end like `/path/to/file:1-` or `/path/to/file:-10`
    """
    global BASH_STATE
    
    # Create ReadFiles object
    read_obj = ReadFiles(
        file_paths=file_paths,
        thread_id=thread_id
    )
    
    # Call the tool
    assert BASH_STATE
    output_or_dones, _ = get_tool_output(
        WCGWContext(BASH_STATE, BASH_STATE.console),
        read_obj,
        default_enc,
        0.0,
        lambda x, y: ("", 0),
        24000,  # coding_max_tokens
        8000,   # noncoding_max_tokens
    )
    
    # Process output
    result = ""
    for output_or_done in output_or_dones:
        if isinstance(output_or_done, str):
            result += output_or_done
    
    return result


# Tool 4: ReadImage
@mcp.tool
async def read_image(
    file_path: str = Field(..., description="Image file path"),
    thread_id: str = Field(default="", description="Thread ID"),
    ctx: Context = None
) -> dict[str, Any]:
    """Read an image from the shell."""
    global BASH_STATE
    
    # Create ReadImage object
    read_img = ReadImage(
        file_path=file_path,
        thread_id=thread_id
    )
    
    # Call the tool
    assert BASH_STATE
    output_or_dones, _ = get_tool_output(
        WCGWContext(BASH_STATE, BASH_STATE.console),
        read_img,
        default_enc,
        0.0,
        lambda x, y: ("", 0),
        24000,  # coding_max_tokens
        8000,   # noncoding_max_tokens
    )
    
    # Process output - expecting ImageData
    for output_or_done in output_or_dones:
        if isinstance(output_or_done, ImageData):
            # Return as dict that FastMCP can handle
            return {
                "type": "image",
                "data": output_or_done.data,
                "mimeType": output_or_done.media_type
            }
        elif isinstance(output_or_done, str):
            # Error case
            return {"type": "error", "message": output_or_done}
    
    return {"type": "error", "message": "No image data returned"}


# Tool 5: FileWriteOrEdit
@mcp.tool
async def file_write_or_edit(
    file_path: str = Field(..., description="File path to write or edit"),
    text_or_search_replace_blocks: str = Field(..., description="Content or search/replace blocks"),
    percentage_to_change: int = Field(..., description="Percentage of lines to change (0-100)", ge=0, le=100),
    thread_id: str = Field(default="", description="Thread ID"),
    ctx: Context = None
) -> str:
    """
    Writes or edits a file based on the percentage of changes.
    - Use absolute path only (~ allowed).
    - First write down percentage of lines that need to be replaced in the file (between 0-100) in percentage_to_change
    - percentage_to_change should be low if mostly new code is to be added. It should be high if a lot of things are to be replaced.
    - If percentage_to_change > 50, provide full file content in text_or_search_replace_blocks
    - If percentage_to_change <= 50, text_or_search_replace_blocks should be search/replace blocks.
    """
    global BASH_STATE
    
    # Create FileWriteOrEdit object
    edit_obj = FileWriteOrEdit(
        file_path=file_path,
        text_or_search_replace_blocks=text_or_search_replace_blocks,
        percentage_to_change=percentage_to_change,
        thread_id=thread_id
    )
    
    # Call the tool
    assert BASH_STATE
    output_or_dones, _ = get_tool_output(
        WCGWContext(BASH_STATE, BASH_STATE.console),
        edit_obj,
        default_enc,
        0.0,
        lambda x, y: ("", 0),
        24000,  # coding_max_tokens
        8000,   # noncoding_max_tokens
    )
    
    # Process output
    result = ""
    for output_or_done in output_or_dones:
        if isinstance(output_or_done, str):
            result += output_or_done
    
    return result


# Tool 6: ContextSave
@mcp.tool
async def context_save(
    task_id: str = Field(..., description="Random 3 word unique id or whatever user provided"),
    file_patterns: list[str] = Field(..., description="File patterns to save"),
    description: str = Field(..., description="Description of the context"),
    project_path: str = Field(default="", description="Project path (empty string if none)"),
    thread_id: str = Field(default="", description="Thread ID"),
    ctx: Context = None
) -> str:
    """
    Saves provided description and file contents of all the relevant file paths or globs in a single text file.
    - Provide random 3 word unique id or whatever user provided.
    - Leave project path as empty string if no project path
    """
    global BASH_STATE
    
    # Create ContextSave object
    save_obj = ContextSave(
        task_id=task_id,
        file_patterns=file_patterns,
        description=description,
        project_path=project_path,
        thread_id=thread_id
    )
    
    # Call the tool
    assert BASH_STATE
    output_or_dones, _ = get_tool_output(
        WCGWContext(BASH_STATE, BASH_STATE.console),
        save_obj,
        default_enc,
        0.0,
        lambda x, y: ("", 0),
        24000,  # coding_max_tokens
        8000,   # noncoding_max_tokens
    )
    
    # Process output
    result = ""
    for output_or_done in output_or_dones:
        if isinstance(output_or_done, str):
            result += output_or_done
    
    return result


# Prompts
@mcp.prompt
async def knowledge_transfer() -> str:
    """Prompt for invoking ContextSave tool in order to do a comprehensive knowledge transfer of a coding task. Prompts to save detailed error log and instructions."""
    assert BASH_STATE
    return KTS[BASH_STATE.mode]


# Main entry point
if __name__ == "__main__":
    import sys
    
    # Check for transport argument
    transport = "http"  # Default to HTTP for remote access
    host = "0.0.0.0"    # Listen on all interfaces
    port = 8000
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--stdio":
            transport = "stdio"
        elif sys.argv[1] == "--help":
            print("Usage: python fastmcp_server.py [--stdio]")
            print("  --stdio: Use stdio transport (default is HTTP)")
            sys.exit(0)
    
    # Run the server
    if transport == "stdio":
        mcp.run()
    else:
        print(f"Starting FastMCP server on http://{host}:{port}/mcp")
        mcp.run(
            transport="http",
            host=host,
            port=port,
            path="/mcp"
        )