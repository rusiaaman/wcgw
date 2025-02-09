import os
from dataclasses import dataclass
from typing import Any

from ..types_ import (
    BashCommand,
    ContextSave,
    FileEdit,
    Initialize,
    ReadFiles,
    ReadImage,
    ResetWcgw,
    WriteIfEmpty,
)

with open(os.path.join(os.path.dirname(__file__), "diff-instructions.txt")) as f:
    diffinstructions = f.read()


@dataclass
class Prompts:
    inputSchema: dict[str, Any]
    name: str
    description: str


TOOL_PROMPTS = [
    Prompts(
        inputSchema=Initialize.model_json_schema(),
        name="Initialize",
        description="""
- Always call this at the start of the conversation before using any of the shell tools from wcgw.
- This will reset the shell.
- Use `any_workspace_path` to initialize the shell in the appropriate project directory.
- If the user has mentioned a workspace or project root, use it to set `any_workspace_path`.
- If the user has mentioned a folder or file with unclear project root, use the file or folder as `any_workspace_path`.
- If user has mentioned any files use `initial_files_to_read` to read, use absolute paths only.
- Leave `any_workspace_path` as empty if no file or folder is mentioned.
- By default use mode "wcgw"
- In "code-writer" mode, set the commands and globs which user asked to set, otherwise use 'all'.
- Call `ResetWcgw` if you want to change the mode later.
""",
    ),
    Prompts(
        inputSchema=BashCommand.model_json_schema(),
        name="BashCommand",
        description="""
- Execute commands and interact with running programs using this unified tool
- The type field specifies the operation:
  - Command: Execute a command
  - StatusCheck: Check status of running command 
  - CommandInteractionText: Send text input
  - CommandInteractionSpecials: Send special keys
  - CommandInteractionAscii: Send raw ASCII codes
- For commands:
  - Status returned at the end
  - May be truncated if too long
  - Use pwd if files not found
  - Use screen for background tasks
  - Use ReadFiles instead of cat
  - Wait for previous commands to finish
  - Only one command allowed at a time
  - Check status if no output (program likely still running)
- For interactions:
  - Only one type of interaction per call
  - Check status before interrupting with Ctrl-c
  - Special keys: Enter, Arrow keys, Ctrl-c/d/z
  - ASCII codes for raw character input
  - Wait appropriate time before interrupting
""",
    ),
    Prompts(
        inputSchema=ReadFiles.model_json_schema(),
        name="ReadFiles",
        description="""
- Read full file content of one or more files.
- Provide absolute file paths only
""",
    ),
    Prompts(
        inputSchema=WriteIfEmpty.model_json_schema(),
        name="WriteIfEmpty",
        description="""
- Write content to an empty or non-existent file. Provide file path and content. Use this instead of BashCommand for writing new files.
- Provide absolute file path only.
- For editing existing files, use FileEdit instead of this tool.
""",
    ),
    Prompts(
        inputSchema=ReadImage.model_json_schema(),
        name="ReadImage",
        description="Read an image from the shell.",
    ),
    Prompts(
        inputSchema=ResetWcgw.model_json_schema(),
        name="ResetWcgw",
        description="Resets the shell. Use either when changing mode, or when all interrupts and prompt reset attempts have failed repeatedly.",
    ),
    Prompts(
        inputSchema=FileEdit.model_json_schema(),
        name="FileEdit",
        description="""
- Use absolute file path only.
- Use SEARCH/REPLACE blocks to edit the file.
- If the edit fails due to block not matching, please retry with correct block till it matches. Re-read the file to ensure you've all the lines correct.
"""
        + diffinstructions,
    ),
    Prompts(
        inputSchema=ContextSave.model_json_schema(),
        name="ContextSave",
        description="""
Saves provided description and file contents of all the relevant file paths or globs in a single text file.
- Provide random unqiue id or whatever user provided.
- Leave project path as empty string if no project path""",
    ),
]
