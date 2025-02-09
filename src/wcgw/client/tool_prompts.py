import os
from dataclasses import dataclass
from typing import Any

from ..types_ import (
    BashCommand,
    BashInteraction,
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
- Execute a bash command. This is stateful (beware with subsequent calls).
- Status of the command and the current working directory will always be returned at the end.
- The first or the last line might be `(...truncated)` if the output is too long.
- Always run `pwd` if you get any file or directory not found error to make sure you're not lost.
- Run long running commands in background using screen instead of "&".
- Do not use 'cat' to read files, use ReadFiles tool instead
- In order to check status of previous command, use `status_check` with empty command argument.
- Only command is allowed to run at a time. You need to wait for any previous command to finish before running a new one.
- Programs don't hang easily, so most likely explanation for no output is usually that the program is still running, and you need to check status again.
""",
    ),
    Prompts(
        inputSchema=BashInteraction.model_json_schema(),
        name="BashInteraction",
        description="""
- Interact with running program using this tool
- Only one of send_text, send_specials, send_ascii should be provided.
- Do not send Ctrl-c before checking for status till 10 minutes or whatever is appropriate for the program to finish.
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
