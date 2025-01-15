import base64
import json
import mimetypes
import os
import subprocess
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Literal, Optional, cast

import rich
from anthropic import Anthropic
from anthropic.types import (
    ImageBlockParam,
    MessageParam,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
)
from dotenv import load_dotenv
from typer import Typer

from ..types_ import (
    BashCommand,
    BashInteraction,
    ContextSave,
    FileEdit,
    GetScreenInfo,
    Keyboard,
    Mouse,
    ReadFiles,
    ReadImage,
    ResetShell,
    ScreenShot,
    WriteIfEmpty,
)
from .common import discard_input
from .memory import load_memory
from .tools import (
    DoneFlag,
    ImageData,
    default_enc,
    get_tool_output,
    initialize,
    which_tool_name,
)

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
                        "media_type": cast(
                            'Literal["image/jpeg", "image/png", "image/gif", "image/webp"]',
                            image_type or "image/png",
                        ),
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
    computer_use: bool = False,
) -> tuple[str, float]:
    load_dotenv()

    session_id = str(uuid.uuid4())[:6]

    history: History = []
    waiting_for_assistant = False
    memory = None
    if resume:
        try:
            _, memory, _ = load_memory(
                resume,
                8000,
                lambda x: default_enc.encode(x).ids,
                lambda x: default_enc.decode(x),
            )
        except OSError:
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

    tools = [
        ToolParam(
            input_schema=BashCommand.model_json_schema(),
            name="BashCommand",
            description="""
- Execute a bash command. This is stateful (beware with subsequent calls).
- Do not use interactive commands like nano. Prefer writing simpler commands.
- Status of the command and the current working directory will always be returned at the end.
- Optionally `exit shell has restarted` is the output, in which case environment resets, you can run fresh commands.
- The first or the last line might be `(...truncated)` if the output is too long.
- Always run `pwd` if you get any file or directory not found error to make sure you're not lost.
- The control will return to you in 5 seconds regardless of the status. For heavy commands, keep checking status using BashInteraction till they are finished.
- Run long running commands in background using screen instead of "&".
- Use longer wait_for_seconds if the command is expected to run for a long time.
- Do not use 'cat' to read files, use ReadFiles tool instead.
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
- This returns within 5 seconds, for heavy programs keep checking status for upto 10 turns before asking user to continue checking again.
- Programs don't hang easily, so most likely explanation for no output is usually that the program is still running, and you need to check status again using ["Enter"].
- Do not send Ctrl-c before checking for status till 10 minutes or whatever is appropriate for the program to finish.
- Set longer wait_for_seconds when program is expected to run for a long time.
""",
        ),
        ToolParam(
            input_schema=ReadFiles.model_json_schema(),
            name="ReadFiles",
            description="""
- Read full file content of one or more files.
- Provide absolute file paths only
""",
        ),
        ToolParam(
            input_schema=WriteIfEmpty.model_json_schema(),
            name="WriteIfEmpty",
            description="""
- Write content to an empty or non-existent file. Provide file path and content. Use this instead of BashCommand for writing new files.
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
- If the edit fails due to block not matching, please retry with correct block till it matches. Re-read the file to ensure you've all the lines correct.
""",
        ),
        ToolParam(
            input_schema=ContextSave.model_json_schema(),
            name="ContextSave",
            description="""
Saves provided description and file contents of all the relevant file paths or globs in a single text file.
- Provide random unqiue id or whatever user provided.
- Leave project path as empty string if no project path
""",
        ),
    ]

    if computer_use:
        tools += [
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
- All actions on UI using mouse and keyboard return within 0.5 seconds.
    * So if you're doing something that takes longer for UI to update like heavy page loading, keep checking UI for update using ScreenShot upto 10 turns. 
    * Notice for smallest of the loading icons to check if your action worked.
    * After 10 turns of no change, ask user for permission to keep checking.
    * If you don't notice even slightest of the change, it's likely you clicked on the wrong place.

""",
            ),
            ToolParam(
                input_schema=Mouse.model_json_schema(),
                name="Mouse",
                description="""
- Interact with the linux os on docker using mouse.
- Uses xdotool
- About left_click_drag: the current mouse position will be used as the starting point, click and drag to the given x, y coordinates. Useful in things like sliders, moving things around, etc.
- The output of this command has the screenshot after doing this action. Use this to verify if the action was successful.
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
- Make sure you've selected a text area or an editable element before sending text.
- The output of this command has the screenshot after doing this action. Use this to verify if the action was successful.
""",
            ),
        ]

    system = initialize(
        os.getcwd(),
        [],
        resume if (memory and resume) else "",
        max_tokens=8000,
        mode="wcgw",
    )

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
                    elif type_ == "content_block_start" and hasattr(
                        chunk, "content_block"
                    ):
                        content_block = chunk.content_block
                        if (
                            hasattr(content_block, "type")
                            and content_block.type == "text"
                            and hasattr(content_block, "text")
                        ):
                            chunk_str = content_block.text
                            assistant_console.print(chunk_str, end="")
                            full_response += chunk_str
                        elif content_block.type == "tool_use":
                            if (
                                hasattr(content_block, "input")
                                and hasattr(content_block, "name")
                                and hasattr(content_block, "id")
                            ):
                                assert content_block.input == {}
                                tool_calls.append(
                                    {
                                        "name": str(content_block.name),
                                        "input": str(""),
                                        "done": False,
                                        "id": str(content_block.id),
                                    }
                                )
                        else:
                            error_console.log(
                                f"Ignoring unknown content block type {content_block.type}"
                            )
                    elif type_ == "content_block_delta" and hasattr(chunk, "delta"):
                        delta = chunk.delta
                        if hasattr(delta, "type"):
                            delta_type = str(delta.type)
                            if delta_type == "text_delta" and hasattr(delta, "text"):
                                chunk_str = delta.text
                                assistant_console.print(chunk_str, end="")
                                full_response += chunk_str
                            elif delta_type == "input_json_delta" and hasattr(
                                delta, "partial_json"
                            ):
                                partial_json = delta.partial_json
                                if isinstance(tool_calls[-1]["input"], str):
                                    tool_calls[-1]["input"] += partial_json
                            else:
                                error_console.log(
                                    f"Ignoring unknown content block delta type {delta_type}"
                                )
                        else:
                            raise ValueError("Content block delta has no type")
                    elif type_ == "content_block_stop":
                        if tool_calls and not tool_calls[-1]["done"]:
                            tc = tool_calls[-1]
                            tool_name = str(tc["name"])
                            tool_input = str(tc["input"])
                            tool_id = str(tc["id"])

                            tool_parsed = which_tool_name(
                                tool_name
                            ).model_validate_json(tool_input)

                            system_console.print(
                                f"\n---------------------------------------\n# Assistant invoked tool: {tool_parsed}"
                            )

                            _histories.append(
                                {
                                    "role": "assistant",
                                    "content": [
                                        ToolUseBlockParam(
                                            id=tool_id,
                                            name=tool_name,
                                            input=tool_parsed.model_dump(),
                                            type="tool_use",
                                        )
                                    ],
                                }
                            )
                            try:
                                output_or_dones, _ = get_tool_output(
                                    tool_parsed,
                                    default_enc,
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
                                    tool_use_id=str(tc["id"]),
                                    content=tool_results_content,
                                )
                            )
                        else:
                            _histories.append(
                                {
                                    "role": "assistant",
                                    "content": full_response
                                    if full_response.strip()
                                    else "...",
                                }  # Fixes anthropic issue of non empty response only
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
