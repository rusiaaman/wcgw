import base64
import json
import mimetypes
from pathlib import Path
import sys
import traceback
from typing import Callable, DefaultDict, Optional, cast
import anthropic
from anthropic import Anthropic
from anthropic.types import (
    ToolParam,
    MessageParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
    ImageBlockParam,
    TextBlockParam,
)

import rich
import petname  # type: ignore[import-untyped]
from typer import Typer
import uuid

from ..types_ import (
    BashCommand,
    BashInteraction,
    CreateFileNew,
    FileEditFindReplace,
    FileEdit,
    Keyboard,
    Mouse,
    ReadFile,
    ReadImage,
    ResetShell,
    ScreenShot,
    GetScreenInfo,
)

from .common import Models, discard_input
from .common import CostData
from .tools import ImageData
from .computer_use import Computer

from .tools import (
    DoneFlag,
    get_tool_output,
    SHELL,
    start_shell,
    which_tool_name,
)
import tiktoken

from urllib import parse
import subprocess
import os
import tempfile

import toml
from pydantic import BaseModel


from dotenv import load_dotenv


History = list[MessageParam]


def text_from_editor(console: rich.console.Console) -> str:
    # First consume all the input till now
    discard_input()
    console.print("\n---------------------------------------\n# User message")
    data = input()
    if data:
        return data
    editor = os.environ.get("EDITOR", "vim")
    with tempfile.NamedTemporaryFile(suffix=".tmp") as tf:
        subprocess.run([editor, tf.name], check=True)
        with open(tf.name, "r") as f:
            data = f.read()
            console.print(data)
            return data


def save_history(history: History, session_id: str) -> None:
    myid = str(history[1]["content"]).replace("/", "_").replace(" ", "_").lower()[:60]
    myid += "_" + session_id
    myid = myid + ".json"

    mypath = Path(".wcgw") / myid
    mypath.parent.mkdir(parents=True, exist_ok=True)
    with open(mypath, "w") as f:
        json.dump(history, f, indent=3)


def parse_user_message_special(msg: str) -> MessageParam:
    # Search for lines starting with `%` and treat them as special commands
    parts: list[ImageBlockParam | TextBlockParam] = []
    for line in msg.split("\n"):
        if line.startswith("%"):
            args = line[1:].strip().split(" ")
            command = args[0]
            assert command == "image"
            image_path = " ".join(args[1:])
            with open(image_path, "rb") as f:
                image_bytes = f.read()
                image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                image_type = mimetypes.guess_type(image_path)[0]
            parts.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_type,
                        "data": image_b64,
                    },
                }
            )
        else:
            if len(parts) > 0 and parts[-1]["type"] == "text":
                parts[-1]["text"] += "\n" + line
            else:
                parts.append({"type": "text", "text": line})
    return {"role": "user", "content": parts}


app = Typer(pretty_exceptions_show_locals=False)


@app.command()
def loop(
    first_message: Optional[str] = None,
    limit: Optional[float] = None,
    resume: Optional[str] = None,
) -> tuple[str, float]:
    load_dotenv()

    session_id = str(uuid.uuid4())[:6]

    history: History = []
    waiting_for_assistant = False
    if resume:
        if resume == "latest":
            resume_path = sorted(Path(".wcgw").iterdir(), key=os.path.getmtime)[-1]
        else:
            resume_path = Path(resume)
        if not resume_path.exists():
            raise FileNotFoundError(f"File {resume} not found")
        with resume_path.open() as f:
            history = json.load(f)
        if len(history) <= 2:
            raise ValueError("Invalid history file")
        first_message = ""
        waiting_for_assistant = history[-1]["role"] != "assistant"

    limit = 1

    enc = tiktoken.encoding_for_model(
        "gpt-4o-2024-08-06",
    )

    tools = [
        ToolParam(
            input_schema=BashCommand.model_json_schema(),
            name="BashCommand",
            description="""
- Execute a bash command. This is stateful (beware with subsequent calls).
- Do not use interactive commands like nano. Prefer writing simpler commands.
- Status of the command and the current working directory will always be returned at the end.
- Optionally `exit shell has restarted` is the output, in which case environment resets, you can run fresh commands.
- The first line might be `(...truncated)` if the output is too long.
- Always run `pwd` if you get any file or directory not found error to make sure you're not lost.
- The control will return to you in 5 seconds regardless of the status. For heavy commands, keep checking status using BashInteraction till they are finished.
- Run long running commands in background using screen instead of "&".
""",
        ),
        ToolParam(
            input_schema=BashInteraction.model_json_schema(),
            name="BashInteraction",
            description="""
- Interact with running program using this tool
- Special keys like arrows, interrupts, enter, etc.
- Send text input to the running program.
- Send send_specials=["Enter"] to recheck status of a running program.
- Only one of send_text, send_specials, send_ascii should be provided.
""",
        ),
        ToolParam(
            input_schema=ReadFile.model_json_schema(),
            name="ReadFile",
            description="""
- Read full file content
- Provide absolute file path only
""",
        ),
        ToolParam(
            input_schema=CreateFileNew.model_json_schema(),
            name="CreateFileNew",
            description="""
- Write content to a new file. Provide file path and content. Use this instead of BashCommand for writing new files.
- Provide absolute file path only.
- For editing existing files, use FileEdit instead of this tool.
""",
        ),
        ToolParam(
            input_schema=ReadImage.model_json_schema(),
            name="ReadImage",
            description="Read an image from the shell.",
        ),
        ToolParam(
            input_schema=ResetShell.model_json_schema(),
            name="ResetShell",
            description="Resets the shell. Use only if all interrupts and prompt reset attempts have failed repeatedly.\nAlso exits the docker environment.\nYou need to call GetScreenInfo again",
        ),
        ToolParam(
            input_schema=FileEdit.model_json_schema(),
            name="FileEdit",
            description="""
- Use absolute file path only.
- Use SEARCH/REPLACE blocks to edit the file.
""",
        ),
        ToolParam(
            input_schema=GetScreenInfo.model_json_schema(),
            name="GetScreenInfo",
            description="""
- Important: call this first in the conversation before ScreenShot, Mouse, and Keyboard tools.
- Get display information of a linux os running on docker using image "ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest"
- If user hasn't provided docker image id, check using `docker ps` and provide the id.
- If the docker is not running, run using `docker run -d -p 6080:6080 ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest`
- Connects shell to the docker environment.
- Note: once this is called, the shell enters the docker environment. All bash commands will run over there.
""",
        ),
        ToolParam(
            input_schema=ScreenShot.model_json_schema(),
            name="ScreenShot",
            description="""
- Capture screenshot of the linux os on docker.
""",
        ),
        ToolParam(
            input_schema=Mouse.model_json_schema(),
            name="Mouse",
            description="""
- Interact with the linux os on docker using mouse.
- Uses xdotool
""",
        ),
        ToolParam(
            input_schema=Keyboard.model_json_schema(),
            name="Keyboard",
            description="""
- Interact with the linux os on docker using keyboard.
- Emulate keyboard input to the screen
- Uses xdootool to send keyboard input, keys like Return, BackSpace, Escape, Page_Up, etc. can be used.
- Do not use it to interact with Bash tool.
""",
        ),
    ]
    uname_sysname = os.uname().sysname
    uname_machine = os.uname().machine

    system = f"""
You're an expert software engineer with shell and code knowledge.

Instructions:

    - You should use the provided bash execution, reading and writing file tools to complete objective.
    - First understand about the project by getting the folder structure (ignoring .git, node_modules, venv, etc.)
    - Always read relevant files before editing.
    - Do not provide code snippets unless asked by the user, instead directly edit the code.

System information:
    - System: {uname_sysname}
    - Machine: {uname_machine}
    - Current directory: {os.getcwd()}
"""

    with open(os.path.join(os.path.dirname(__file__), "diff-instructions.txt")) as f:
        system += f.read()

    if history:
        if (
            (last_msg := history[-1])["role"] == "user"
            and isinstance((content := last_msg["content"]), dict)
            and content["type"] == "tool_result"
        ):
            waiting_for_assistant = True

    client = Anthropic()

    cost: float = 0
    input_toks = 0
    output_toks = 0
    system_console = rich.console.Console(style="blue", highlight=False, markup=False)
    error_console = rich.console.Console(style="red", highlight=False, markup=False)
    user_console = rich.console.Console(
        style="bright_black", highlight=False, markup=False
    )
    assistant_console = rich.console.Console(
        style="white bold", highlight=False, markup=False
    )
    while True:
        if cost > limit:
            system_console.print(
                f"\nCost limit exceeded. Current cost: {cost}, input tokens: {input_toks}, output tokens: {output_toks}"
            )
            break

        if not waiting_for_assistant:
            if first_message:
                msg = first_message
                first_message = ""
            else:
                msg = text_from_editor(user_console)

            history.append(parse_user_message_special(msg))
        else:
            waiting_for_assistant = False

        cost_, input_toks_ = 0, 0
        cost += cost_
        input_toks += input_toks_

        stream = client.messages.stream(
            model="claude-3-5-sonnet-20241022",
            messages=history,
            tools=tools,
            max_tokens=8096,
            system=system,
        )

        system_console.print(
            "\n---------------------------------------\n# Assistant response",
            style="bold",
        )
        _histories: History = []
        full_response: str = ""

        tool_calls = []
        tool_results: list[ToolResultBlockParam] = []
        try:
            with stream as stream_:
                for chunk in stream_:
                    type_ = chunk.type
                    if type_ in {"message_start", "message_stop"}:
                        continue
                    elif type_ == "content_block_start":
                        content_block = chunk.content_block
                        if content_block.type == "text":
                            chunk_str = content_block.text
                            assistant_console.print(chunk_str, end="")
                            full_response += chunk_str
                        elif content_block.type == "tool_use":
                            assert content_block.input == {}
                            tool_calls.append(
                                {
                                    "name": content_block.name,
                                    "input": "",
                                    "done": False,
                                    "id": content_block.id,
                                }
                            )
                        else:
                            error_console.log(
                                f"Ignoring unknown content block type {content_block.type}"
                            )
                    elif type_ == "content_block_delta":
                        if chunk.delta.type == "text_delta":
                            chunk_str = chunk.delta.text
                            assistant_console.print(chunk_str, end="")
                            full_response += chunk_str
                        elif chunk.delta.type == "input_json_delta":
                            tool_calls[-1]["input"] += chunk.delta.partial_json
                        else:
                            error_console.log(
                                f"Ignoring unknown content block delta type {chunk.delta.type}"
                            )
                    elif type_ == "content_block_stop":
                        if tool_calls and not tool_calls[-1]["done"]:
                            tc = tool_calls[-1]
                            tool_parsed = which_tool_name(
                                tc["name"]
                            ).model_validate_json(tc["input"])
                            system_console.print(
                                f"\n---------------------------------------\n# Assistant invoked tool: {tool_parsed}"
                            )
                            _histories.append(
                                {
                                    "role": "assistant",
                                    "content": [
                                        ToolUseBlockParam(
                                            id=tc["id"],
                                            name=tc["name"],
                                            input=tool_parsed.model_dump(),
                                            type="tool_use",
                                        )
                                    ],
                                }
                            )
                            try:
                                output_or_dones, _ = get_tool_output(
                                    tool_parsed,
                                    enc,
                                    limit - cost,
                                    loop,
                                    max_tokens=8000,
                                )
                            except Exception as e:
                                output_or_dones = [
                                    (f"GOT EXCEPTION while calling tool. Error: {e}")
                                ]
                                tb = traceback.format_exc()
                                error_console.print(str(output_or_dones) + "\n" + tb)

                            if any(isinstance(x, DoneFlag) for x in output_or_dones):
                                return "", cost

                            tool_results_content: list[
                                TextBlockParam | ImageBlockParam
                            ] = []
                            for output in output_or_dones:
                                assert not isinstance(output, DoneFlag)
                                if isinstance(output, ImageData):
                                    tool_results_content.append(
                                        {
                                            "type": "image",
                                            "source": {
                                                "type": "base64",
                                                "media_type": output.media_type,
                                                "data": output.data,
                                            },
                                        }
                                    )

                                else:
                                    tool_results_content.append(
                                        {
                                            "type": "text",
                                            "text": output,
                                        },
                                    )
                            tool_results.append(
                                ToolResultBlockParam(
                                    type="tool_result",
                                    tool_use_id=tc["id"],
                                    content=tool_results_content,
                                )
                            )
                        else:
                            _histories.append(
                                {"role": "assistant", "content": full_response}
                            )

        except KeyboardInterrupt:
            waiting_for_assistant = False
            input("Interrupted...enter to redo the current turn")
        else:
            history.extend(_histories)
            if tool_results:
                history.append({"role": "user", "content": tool_results})
                waiting_for_assistant = True
            save_history(history, session_id)

    return "Couldn't finish the task", cost


if __name__ == "__main__":
    app()
