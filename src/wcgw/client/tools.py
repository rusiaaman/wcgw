import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import re
import sys
import threading
import importlib.metadata
import time
import traceback
from typing import (
    Callable,
    Literal,
    NewType,
    Optional,
    ParamSpec,
    Type,
    TypeVar,
    TypedDict,
)
import uuid
from pydantic import BaseModel, TypeAdapter
import typer
from websockets.sync.client import connect as syncconnect

import os
import tiktoken
import petname  # type: ignore[import-untyped]
import pexpect
from typer import Typer
import websockets

import rich
import pyte
from dotenv import load_dotenv

import openai
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ParsedChatCompletionMessage,
)
from nltk.metrics.distance import edit_distance

from ..types_ import (
    CreateFileNew,
    FileEditFindReplace,
    FullFileEdit,
    ResetShell,
    Writefile,
)

from ..types_ import BashCommand

from ..types_ import BashInteraction

from ..types_ import ReadImage

from .common import CostData, Models, discard_input

from .openai_utils import get_input_cost, get_output_cost

console = rich.console.Console(style="magenta", highlight=False, markup=False)

TIMEOUT = 30


def render_terminal_output(text: str) -> str:
    screen = pyte.Screen(160, 500)
    screen.set_mode(pyte.modes.LNM)
    stream = pyte.Stream(screen)
    stream.feed(text)
    # Filter out empty lines
    dsp = screen.display[::-1]
    for i, line in enumerate(dsp):
        if line.strip():
            break
    else:
        i = len(dsp)
    lines = screen.display[: len(dsp) - i]
    # Strip trailing space
    lines = [line.rstrip() for line in lines]
    return "\n".join(lines)


class Confirmation(BaseModel):
    prompt: str


def ask_confirmation(prompt: Confirmation) -> str:
    response = input(prompt.prompt + " [y/n] ")
    return "Yes" if response.lower() == "y" else "No"


PROMPT = "#@@"


def start_shell() -> pexpect.spawn:  # type: ignore
    SHELL = pexpect.spawn(
        "/bin/bash --noprofile --norc",
        env={**os.environ, **{"PS1": PROMPT}},  # type: ignore[arg-type]
        echo=False,
        encoding="utf-8",
        timeout=TIMEOUT,
    )
    SHELL.expect(PROMPT)
    SHELL.sendline("stty -icanon -echo")
    SHELL.expect(PROMPT)
    return SHELL


SHELL = start_shell()


def _is_int(mystr: str) -> bool:
    try:
        int(mystr)
        return True
    except ValueError:
        return False


def _get_exit_code() -> int:
    if PROMPT != "#@@":
        return 0
    # First reset the prompt in case venv was sourced or other reasons.
    SHELL.sendline(f"export PS1={PROMPT}")
    SHELL.expect(PROMPT)
    # Reset echo also if it was enabled
    SHELL.sendline("stty -icanon -echo")
    SHELL.expect(PROMPT)
    SHELL.sendline("echo $?")
    before = ""
    while not _is_int(before):  # Consume all previous output
        try:
            SHELL.expect(PROMPT)
        except pexpect.TIMEOUT:
            print(f"Couldn't get exit code, before: {before}")
            raise
        assert isinstance(SHELL.before, str)
        # Render because there could be some anscii escape sequences still set like in google colab env
        before = render_terminal_output(SHELL.before).strip()

    try:
        return int((before))
    except ValueError:
        raise ValueError(f"Malformed output: {before}")


BASH_CLF_OUTPUT = Literal["repl", "pending"]
BASH_STATE: BASH_CLF_OUTPUT = "repl"
CWD = os.getcwd()


def reset_shell() -> str:
    global SHELL, BASH_STATE, CWD
    SHELL.close(True)
    SHELL = start_shell()
    BASH_STATE = "repl"
    CWD = os.getcwd()
    return "Reset successful" + get_status()


WAITING_INPUT_MESSAGE = """A command is already running. NOTE: You can't run multiple shell sessions, likely a previous program hasn't exited. 
1. Get its output using `send_ascii: [10] or send_specials: ["Enter"]`
2. Use `send_ascii` or `send_specials` to give inputs to the running program, don't use `BashCommand` OR
3. kill the previous program by sending ctrl+c first using `send_ascii` or `send_specials`
4. Send the process in background using `send_specials: ["Ctrl-z"]` followed by BashCommand: `bg`
"""


def update_repl_prompt(command: str) -> bool:
    global PROMPT
    if re.match(r"^wcgw_update_prompt\(\)$", command.strip()):
        SHELL.sendintr()
        index = SHELL.expect([PROMPT, pexpect.TIMEOUT], timeout=0.2)
        if index == 0:
            return False
        before = SHELL.before or ""
        assert before, "Something went wrong updating repl prompt"
        PROMPT = before.split("\n")[-1].strip()
        # Escape all regex
        PROMPT = re.escape(PROMPT)
        print(f"Trying to update prompt to: {PROMPT.encode()!r}")
        index = 0
        while index == 0:
            # Consume all REPL prompts till now
            index = SHELL.expect([PROMPT, pexpect.TIMEOUT], timeout=0.2)
        print(f"Prompt updated to: {PROMPT}")
        return True
    return False


def get_cwd() -> str:
    SHELL.sendline("pwd")
    SHELL.expect(PROMPT)
    assert isinstance(SHELL.before, str)
    current_dir = render_terminal_output(SHELL.before).strip()
    return current_dir


def get_status() -> str:
    global CWD
    exit_code: Optional[int] = None

    status = "\n\n---\n\n"
    if BASH_STATE == "pending":
        status += "status = still running\n"
        status += "cwd = " + CWD + "\n"
    else:
        exit_code = _get_exit_code()
        status += f"status = exited with code {exit_code}\n"
        CWD = get_cwd()
        status += "cwd = " + CWD + "\n"

    return status.rstrip()


def execute_bash(
    enc: tiktoken.Encoding,
    bash_arg: BashCommand | BashInteraction,
    max_tokens: Optional[int],
) -> tuple[str, float]:
    global SHELL, BASH_STATE, CWD
    try:
        is_interrupt = False
        if isinstance(bash_arg, BashCommand):
            updated_repl_mode = update_repl_prompt(bash_arg.command)
            if updated_repl_mode:
                BASH_STATE = "repl"
                response = (
                    "Prompt updated, you can execute REPL lines using BashCommand now"
                )
                console.print(response)
                return (
                    response,
                    0,
                )

            console.print(f"$ {bash_arg.command}")
            if BASH_STATE == "pending":
                raise ValueError(WAITING_INPUT_MESSAGE)
            command = bash_arg.command.strip()

            if "\n" in command:
                raise ValueError(
                    "Command should not contain newline character in middle. Run only one command at a time."
                )

            SHELL.sendline(command)
        elif bash_arg.send_specials:
            console.print(f"Sending special sequence: {bash_arg.send_specials}")
            for char in bash_arg.send_specials:
                if char == "Key-up":
                    SHELL.send("\033[A")
                elif char == "Key-down":
                    SHELL.send("\033[B")
                elif char == "Key-left":
                    SHELL.send("\033[D")
                elif char == "Key-right":
                    SHELL.send("\033[C")
                elif char == "Enter":
                    SHELL.send("\n")
                elif char == "Ctrl-c":
                    SHELL.sendintr()
                    is_interrupt = True
                elif char == "Ctrl-d":
                    SHELL.sendintr()
                    is_interrupt = True
                elif char == "Ctrl-z":
                    SHELL.send("\x1a")
                else:
                    raise Exception(f"Unknown special character: {char}")
        elif bash_arg.send_ascii:
            console.print(f"Sending ASCII sequence: {bash_arg.send_ascii}")
            for ascii_char in bash_arg.send_ascii:
                SHELL.send(chr(ascii_char))
                if ascii_char == 3:
                    is_interrupt = True
        else:
            if bash_arg.send_text is None:
                return (
                    "Failure: at least one of send_text, send_specials or send_ascii should be provided",
                    0.0,
                )

            updated_repl_mode = update_repl_prompt(bash_arg.send_text)
            if updated_repl_mode:
                BASH_STATE = "repl"
                response = (
                    "Prompt updated, you can execute REPL lines using BashCommand now"
                )
                console.print(response)
                return (
                    response,
                    0,
                )
            console.print(f"Interact text: {bash_arg.send_text}")
            SHELL.sendline(bash_arg.send_text)

        BASH_STATE = "repl"

    except KeyboardInterrupt:
        SHELL.sendintr()
        SHELL.expect(PROMPT)
        return "---\n\nFailure: user interrupted the execution", 0.0

    wait = 5
    index = SHELL.expect([PROMPT, pexpect.TIMEOUT], timeout=wait)
    if index == 1:
        BASH_STATE = "pending"
        text = SHELL.before or ""

        text = render_terminal_output(text)
        tokens = enc.encode(text)

        if max_tokens and len(tokens) >= max_tokens:
            text = "...(truncated)\n" + enc.decode(tokens[-(max_tokens - 1) :])

        if is_interrupt:
            text = (
                text
                + """---
----
Failure interrupting.
If any REPL session was previously running or if bashrc was sourced, or if there is issue to other REPL related reasons:
    Run BashCommand: "wcgw_update_prompt()" to reset the PS1 prompt.
Otherwise, you may want to try Ctrl-c again or program specific exit interactive commands.
"""
            )

        exit_status = get_status()
        text += exit_status

        return text, 0

    if is_interrupt:
        return "Interrupt successful", 0.0

    assert isinstance(SHELL.before, str)
    output = render_terminal_output(SHELL.before)

    tokens = enc.encode(output)
    if max_tokens and len(tokens) >= max_tokens:
        output = "...(truncated)\n" + enc.decode(tokens[-(max_tokens - 1) :])

    try:
        exit_status = get_status()
        output += exit_status
    except ValueError as e:
        console.print(output)
        traceback.print_exc()
        console.print("Malformed output, restarting shell", style="red")
        # Malformed output, restart shell
        SHELL.close(True)
        SHELL = start_shell()
        output = "(exit shell has restarted)"
    return output, 0


def serve_image_in_bg(file_path: str, client_uuid: str, name: str) -> None:
    if not client_uuid:
        client_uuid = str(uuid.uuid4())

    server_url = "wss://wcgw.arcfu.com/register_serve_image"

    with open(file_path, "rb") as image_file:
        image_bytes = image_file.read()
        media_type = mimetypes.guess_type(file_path)[0]
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        uu = {"name": name, "image_b64": image_b64, "media_type": media_type}

    with syncconnect(f"{server_url}/{client_uuid}") as websocket:
        try:
            websocket.send(json.dumps(uu))
        except websockets.ConnectionClosed:
            print(f"Connection closed for UUID: {client_uuid}, retrying")
            serve_image_in_bg(file_path, client_uuid, name)


MEDIA_TYPES = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]


class ImageData(BaseModel):
    media_type: MEDIA_TYPES
    data: str

    @property
    def dataurl(self) -> str:
        return f"data:{self.media_type};base64," + self.data


Param = ParamSpec("Param")

T = TypeVar("T")


def ensure_no_previous_output(func: Callable[Param, T]) -> Callable[Param, T]:
    def wrapper(*args: Param.args, **kwargs: Param.kwargs) -> T:
        global BASH_STATE
        if BASH_STATE == "pending":
            raise ValueError(WAITING_INPUT_MESSAGE)

        return func(*args, **kwargs)

    return wrapper


def read_image_from_shell(file_path: str) -> ImageData:
    if not os.path.isabs(file_path):
        file_path = os.path.join(CWD, file_path)

    if not os.path.exists(file_path):
        raise ValueError(f"File {file_path} does not exist")

    with open(file_path, "rb") as image_file:
        image_bytes = image_file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_type = mimetypes.guess_type(file_path)[0]
        return ImageData(media_type=image_type, data=image_b64)


def write_file(writefile: Writefile | CreateFileNew, error_on_exist: bool) -> str:
    if not os.path.isabs(writefile.file_path):
        return "Failure: file_path should be absolute path"
    else:
        path_ = writefile.file_path

    if error_on_exist and os.path.exists(path_):
        file_data = Path(path_).read_text()
        if file_data:
            return f"Error: can't write to existing file {path_}, use other functions to edit the file"

    path = Path(path_)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with path.open("w") as f:
            f.write(writefile.file_content)
    except OSError as e:
        return f"Error: {e}"
    console.print(f"File written to {path_}")
    return "Success"


def find_least_edit_distance_substring(
    content: str, find_str: str
) -> tuple[str, float]:
    orig_content_lines = content.split("\n")
    content_lines = [
        line.strip() for line in orig_content_lines
    ]  # Remove trailing and leading space for calculating edit distance
    find_lines = find_str.split("\n")
    find_lines = [
        line.strip() for line in find_lines
    ]  # Remove trailing and leading space for calculating edit distance
    # Slide window and find one with sum of edit distance least
    min_edit_distance = float("inf")
    min_edit_distance_lines = []
    for i in range(max(1, len(content_lines) - len(find_lines) + 1)):
        edit_distance_sum = 0
        for j in range(len(find_lines)):
            if (i + j) < len(content_lines):
                edit_distance_sum += edit_distance(content_lines[i + j], find_lines[j])
            else:
                edit_distance_sum += len(find_lines[j])
        if edit_distance_sum < min_edit_distance:
            min_edit_distance = edit_distance_sum
            min_edit_distance_lines = orig_content_lines[i : i + len(find_lines)]
    return "\n".join(min_edit_distance_lines), min_edit_distance


def edit_content(content: str, find_lines: str, replace_with_lines: str) -> str:
    count = content.count(find_lines)
    if count == 0:
        closest_match, min_edit_distance = find_least_edit_distance_substring(
            content, find_lines
        )
        print(
            f"Exact match not found, found with whitespace removed edit distance: {min_edit_distance}"
        )
        if min_edit_distance / len(find_lines) < 1 / 100:
            print("Editing file with closest match")
            return edit_content(content, closest_match, replace_with_lines)
        raise Exception(
            f"Error: no match found for the provided `find_lines` in the file. Closest match:\n---\n{closest_match}\n---\nFile not edited"
        )

    content = content.replace(find_lines, replace_with_lines, 1)
    return content


def do_diff_edit(fedit: FullFileEdit) -> str:
    console.log(f"Editing file: {fedit.file_path}")

    if not os.path.isabs(fedit.file_path):
        raise Exception("Failure: file_path should be absolute path")
    else:
        path_ = fedit.file_path

    if not os.path.exists(path_):
        raise Exception(f"Error: file {path_} does not exist")

    with open(path_) as f:
        apply_diff_to = f.read()

    lines = fedit.file_edit_using_searh_replace_blocks.split("\n")
    n_lines = len(lines)
    i = 0
    while i < n_lines:
        if re.match(r"^<<<<<<+\s*SEARCH\s*$", lines[i]):
            search_block = []
            i += 1
            while i < n_lines and not re.match(r"^======*\s*$", lines[i]):
                search_block.append(lines[i])
                i += 1
            i += 1
            replace_block = []
            while i < n_lines and not re.match(r"^>>>>>>+\s*REPLACE\s*$", lines[i]):
                replace_block.append(lines[i])
                i += 1
            i += 1

            for line in search_block:
                console.log("> " + line)
            console.log("---")
            for line in replace_block:
                console.log("< " + line)

            search_block_ = "\n".join(search_block)
            replace_block_ = "\n".join(replace_block)

            apply_diff_to = edit_content(apply_diff_to, search_block_, replace_block_)
        else:
            i += 1

    with open(path_, "w") as f:
        f.write(apply_diff_to)

    return "Success"


def file_edit(fedit: FileEditFindReplace) -> str:
    if not os.path.isabs(fedit.file_path):
        raise Exception("Failure: file_path should be absolute path")
    else:
        path_ = fedit.file_path

    if not os.path.exists(path_):
        raise Exception(f"Error: file {path_} does not exist")

    if not fedit.find_lines:
        raise Exception("Error: `find_lines` cannot be empty")

    out_string = "\n".join("> " + line for line in fedit.find_lines.split("\n"))
    in_string = "\n".join("< " + line for line in fedit.replace_with_lines.split("\n"))
    console.log(f"Editing file: {path_}\n---\n{out_string}\n---\n{in_string}\n---")
    try:
        with open(path_) as f:
            content = f.read()

        content = edit_content(content, fedit.find_lines, fedit.replace_with_lines)

        with open(path_, "w") as f:
            f.write(content)
    except OSError as e:
        raise Exception(f"Error: {e}")
    console.print(f"File written to {path_}")
    return "Success"


class DoneFlag(BaseModel):
    task_output: str


def mark_finish(done: DoneFlag) -> DoneFlag:
    return done


class AIAssistant(BaseModel):
    instruction: str
    desired_output: str


def take_help_of_ai_assistant(
    aiassistant: AIAssistant,
    limit: float,
    loop_call: Callable[[str, float], tuple[str, float]],
) -> tuple[str, float]:
    output, cost = loop_call(aiassistant.instruction, limit)
    return output, cost


TOOLS = (
    Confirmation
    | BashCommand
    | BashInteraction
    | ResetShell
    | Writefile
    | CreateFileNew
    | FileEditFindReplace
    | FullFileEdit
    | AIAssistant
    | DoneFlag
    | ReadImage
)


def which_tool(args: str) -> TOOLS:
    adapter = TypeAdapter[TOOLS](TOOLS)
    return adapter.validate_python(json.loads(args))


def which_tool_name(name: str) -> Type[TOOLS]:
    if name == "Confirmation":
        return Confirmation
    elif name == "BashCommand":
        return BashCommand
    elif name == "BashInteraction":
        return BashInteraction
    elif name == "ResetShell":
        return ResetShell
    elif name == "Writefile":
        return Writefile
    elif name == "CreateFileNew":
        return CreateFileNew
    elif name == "FileEditFindReplace":
        return FileEditFindReplace
    elif name == "FullFileEdit":
        return FullFileEdit
    elif name == "AIAssistant":
        return AIAssistant
    elif name == "DoneFlag":
        return DoneFlag
    elif name == "ReadImage":
        return ReadImage
    else:
        raise ValueError(f"Unknown tool name: {name}")


def get_tool_output(
    args: dict[object, object]
    | Confirmation
    | BashCommand
    | BashInteraction
    | ResetShell
    | Writefile
    | CreateFileNew
    | FileEditFindReplace
    | FullFileEdit
    | AIAssistant
    | DoneFlag
    | ReadImage,
    enc: tiktoken.Encoding,
    limit: float,
    loop_call: Callable[[str, float], tuple[str, float]],
    max_tokens: Optional[int],
) -> tuple[str | ImageData | DoneFlag, float]:
    if isinstance(args, dict):
        adapter = TypeAdapter[
            Confirmation
            | BashCommand
            | BashInteraction
            | ResetShell
            | Writefile
            | CreateFileNew
            | FileEditFindReplace
            | FullFileEdit
            | AIAssistant
            | DoneFlag
            | ReadImage
        ](
            Confirmation
            | BashCommand
            | BashInteraction
            | ResetShell
            | Writefile
            | CreateFileNew
            | FileEditFindReplace
            | FullFileEdit
            | AIAssistant
            | DoneFlag
            | ReadImage
        )
        arg = adapter.validate_python(args)
    else:
        arg = args
    output: tuple[str | DoneFlag | ImageData, float]
    if isinstance(arg, Confirmation):
        console.print("Calling ask confirmation tool")
        output = ask_confirmation(arg), 0.0
    elif isinstance(arg, (BashCommand | BashInteraction)):
        console.print("Calling execute bash tool")
        output = execute_bash(enc, arg, max_tokens)
    elif isinstance(arg, Writefile):
        console.print("Calling write file tool")
        output = write_file(arg, False), 0
    elif isinstance(arg, CreateFileNew):
        console.print("Calling write file tool")
        output = write_file(arg, True), 0
    elif isinstance(arg, FileEditFindReplace):
        console.print("Calling file edit tool")
        output = file_edit(arg), 0.0
    elif isinstance(arg, FullFileEdit):
        console.print("Calling full file edit tool")
        output = do_diff_edit(arg), 0.0
    elif isinstance(arg, DoneFlag):
        console.print("Calling mark finish tool")
        output = mark_finish(arg), 0.0
    elif isinstance(arg, AIAssistant):
        console.print("Calling AI assistant tool")
        output = take_help_of_ai_assistant(arg, limit, loop_call)
    elif isinstance(arg, ReadImage):
        console.print("Calling read image tool")
        output = read_image_from_shell(arg.file_path), 0.0
    elif isinstance(arg, ResetShell):
        console.print("Calling reset shell tool")
        output = reset_shell(), 0.0
    else:
        raise ValueError(f"Unknown tool: {arg}")

    console.print(str(output[0]))
    return output


History = list[ChatCompletionMessageParam]

default_enc = tiktoken.encoding_for_model("gpt-4o")
default_model: Models = "gpt-4o-2024-08-06"
default_cost = CostData(cost_per_1m_input_tokens=0.15, cost_per_1m_output_tokens=0.6)
curr_cost = 0.0


class Mdata(BaseModel):
    data: (
        BashCommand
        | BashInteraction
        | Writefile
        | CreateFileNew
        | ResetShell
        | FileEditFindReplace
        | FullFileEdit
        | str
    )


def register_client(server_url: str, client_uuid: str = "") -> None:
    global default_enc, default_model, curr_cost
    # Generate a unique UUID for this client
    if not client_uuid:
        client_uuid = str(uuid.uuid4())

    # Create the WebSocket connection
    try:
        with syncconnect(f"{server_url}/{client_uuid}") as websocket:
            server_version = str(websocket.recv())
            print(f"Server version: {server_version}")
            client_version = importlib.metadata.version("wcgw")
            websocket.send(client_version)

            print(
                f"Connected. Share this user id with the chatbot: {client_uuid} \nLink: https://chatgpt.com/g/g-Us0AAXkRh-wcgw-giving-shell-access"
            )
            while True:
                # Wait to receive data from the server
                message = websocket.recv()
                mdata = Mdata.model_validate_json(message)
                if isinstance(mdata.data, str):
                    raise Exception(mdata)
                try:
                    output, cost = get_tool_output(
                        mdata.data, default_enc, 0.0, lambda x, y: ("", 0), None
                    )
                    curr_cost += cost
                    print(f"{curr_cost=}")
                except Exception as e:
                    output = f"GOT EXCEPTION while calling tool. Error: {e}"
                    traceback.print_exc()
                assert isinstance(output, str)
                websocket.send(output)

    except (websockets.ConnectionClosed, ConnectionError, OSError):
        print(f"Connection closed for UUID: {client_uuid}, retrying")
        time.sleep(0.5)
        register_client(server_url, client_uuid)


run = Typer(pretty_exceptions_show_locals=False, no_args_is_help=True)


@run.command()
def app(
    server_url: str = "wss://wcgw.arcfu.com/v1/register",
    client_uuid: Optional[str] = None,
    version: bool = typer.Option(False, "--version", "-v"),
) -> None:
    if version:
        version_ = importlib.metadata.version("wcgw")
        print(f"wcgw version: {version_}")
        exit()

    register_client(server_url, client_uuid or "")
