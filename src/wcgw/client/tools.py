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
from tempfile import TemporaryDirectory
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
from .computer_use import run_computer_tool
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
from nltk.metrics.distance import edit_distance  # type: ignore[import-untyped]

from ..types_ import (
    BashCommand,
    BashInteraction,
    CreateFileNew,
    FileEditFindReplace,
    FileEdit,
    Initialize,
    ReadFile,
    ReadImage,
    ResetShell,
    Mouse,
    Keyboard,
    ScreenShot,
    GetScreenInfo,
)

from .common import CostData, Models, discard_input
from .sys_utils import command_run
from .openai_utils import get_input_cost, get_output_cost

console = rich.console.Console(style="magenta", highlight=False, markup=False)

TIMEOUT = 5


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


PROMPT_CONST = "#@wcgw@#"
PROMPT = PROMPT_CONST


def start_shell() -> pexpect.spawn:  # type: ignore
    SHELL = pexpect.spawn(
        "/bin/bash --noprofile --norc",
        env={**os.environ, **{"PS1": PROMPT}},  # type: ignore[arg-type]
        echo=False,
        encoding="utf-8",
        timeout=TIMEOUT,
    )
    SHELL.expect(PROMPT, timeout=TIMEOUT)
    SHELL.sendline("stty -icanon -echo")
    SHELL.expect(PROMPT, timeout=TIMEOUT)
    return SHELL


SHELL = start_shell()


def _is_int(mystr: str) -> bool:
    try:
        int(mystr)
        return True
    except ValueError:
        return False


def _get_exit_code() -> int:
    if PROMPT != PROMPT_CONST:
        return 0
    # First reset the prompt in case venv was sourced or other reasons.
    SHELL.sendline(f"export PS1={PROMPT}")
    SHELL.expect(PROMPT, timeout=0.2)
    # Reset echo also if it was enabled
    SHELL.sendline("stty -icanon -echo")
    SHELL.expect(PROMPT, timeout=0.2)
    SHELL.sendline("echo $?")
    before = ""
    while not _is_int(before):  # Consume all previous output
        try:
            SHELL.expect(PROMPT, timeout=0.2)
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
IS_IN_DOCKER: Optional[str] = ""
CWD = os.getcwd()


def initial_info() -> str:
    uname_sysname = os.uname().sysname
    uname_machine = os.uname().machine
    return f"""
System: {uname_sysname}
Machine: {uname_machine}
Current working directory: {CWD}
wcgw version: {importlib.metadata.version("wcgw")}
"""


def reset_shell() -> str:
    global SHELL, BASH_STATE, CWD, IS_IN_DOCKER
    SHELL.close(True)
    SHELL = start_shell()
    BASH_STATE = "repl"
    IS_IN_DOCKER = ""
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
    SHELL.expect(PROMPT, timeout=0.2)
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
    timeout_s: Optional[float],
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

        else:
            if (
                sum(
                    [
                        int(bool(bash_arg.send_text)),
                        int(bool(bash_arg.send_specials)),
                        int(bool(bash_arg.send_ascii)),
                    ]
                )
                != 1
            ):
                return (
                    "Failure: exactly one of send_text, send_specials or send_ascii should be provided",
                    0.0,
                )
            if bash_arg.send_specials:
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
                    response = "Prompt updated, you can execute REPL lines using BashCommand now"
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

    wait = timeout_s or TIMEOUT
    index = SHELL.expect([PROMPT, pexpect.TIMEOUT], timeout=wait)
    if index == 1:
        BASH_STATE = "pending"
        text = SHELL.before or ""

        text = render_terminal_output(text[-100_000:])
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

    if not IS_IN_DOCKER:
        if not os.path.exists(file_path):
            raise ValueError(f"File {file_path} does not exist")

        with open(file_path, "rb") as image_file:
            image_bytes = image_file.read()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            image_type = mimetypes.guess_type(file_path)[0]
            return ImageData(media_type=image_type, data=image_b64)  # type: ignore
    else:
        with TemporaryDirectory() as tmpdir:
            rcode = os.system(f"docker cp {IS_IN_DOCKER}:{file_path} {tmpdir}")
            if rcode != 0:
                raise Exception(f"Error: Read failed with code {rcode}")
            path_ = os.path.join(tmpdir, os.path.basename(file_path))
            with open(path_, "rb") as f:
                image_bytes = f.read()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            image_type = mimetypes.guess_type(file_path)[0]
            return ImageData(media_type=image_type, data=image_b64)  # type: ignore


def write_file(writefile: CreateFileNew, error_on_exist: bool) -> str:
    if not os.path.isabs(writefile.file_path):
        return f"Failure: file_path should be absolute path, current working directory is {CWD}"
    else:
        path_ = writefile.file_path

    if not IS_IN_DOCKER:
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
    else:
        if error_on_exist:
            # Check if it exists using os.system
            cmd = f"test -f {path_}"
            status = os.system(f'docker exec {IS_IN_DOCKER} bash -c "{cmd}"')
            if status == 0:
                return f"Error: can't write to existing file {path_}, use other functions to edit the file"

        with TemporaryDirectory() as tmpdir:
            tmppath = os.path.join(tmpdir, os.path.basename(path_))
            with open(tmppath, "w") as f:
                f.write(writefile.file_content)
            os.chmod(tmppath, 0o777)
            parent_dir = os.path.dirname(path_)
            rcode = os.system(f"docker exec {IS_IN_DOCKER} mkdir -p {parent_dir}")
            if rcode != 0:
                return f"Error: Write failed with code while creating dirs {rcode}"

            rcode = os.system(f"docker cp {tmppath} {IS_IN_DOCKER}:{path_}")
            if rcode != 0:
                return f"Error: Write failed with code {rcode}"

    console.print(f"File written to {path_}")
    return "Success"


def find_least_edit_distance_substring(
    content: str, find_str: str
) -> tuple[str, float]:
    orig_content_lines = content.split("\n")
    content_lines = [
        line.strip() for line in orig_content_lines
    ]  # Remove trailing and leading space for calculating edit distance
    new_to_original_indices = {}
    new_content_lines = []
    for i in range(len(content_lines)):
        if not content_lines[i]:
            continue
        new_content_lines.append(content_lines[i])
        new_to_original_indices[len(new_content_lines) - 1] = i
    content_lines = new_content_lines
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
            orig_start_index = new_to_original_indices[i]
            orig_end_index = (
                new_to_original_indices.get(
                    i + len(find_lines) - 1, len(orig_content_lines) - 1
                )
                + 1
            )
            min_edit_distance_lines = orig_content_lines[
                orig_start_index:orig_end_index
            ]
    return "\n".join(min_edit_distance_lines), min_edit_distance


def edit_content(content: str, find_lines: str, replace_with_lines: str) -> str:
    count = content.count(find_lines)
    if count == 0:
        closest_match, min_edit_distance = find_least_edit_distance_substring(
            content, find_lines
        )
        if min_edit_distance == 0:
            return edit_content(content, closest_match, replace_with_lines)
        else:
            print(
                f"Exact match not found, found with whitespace removed edit distance: {min_edit_distance}"
            )
        raise Exception(
            f"Error: no match found for the provided `find_lines` in the file. Closest match:\n---\n{closest_match}\n---\nFile not edited"
        )

    content = content.replace(find_lines, replace_with_lines, 1)
    return content


def do_diff_edit(fedit: FileEdit) -> str:
    console.log(f"Editing file: {fedit.file_path}")

    if not os.path.isabs(fedit.file_path):
        raise Exception(
            f"Failure: file_path should be absolute path, current working directory is {CWD}"
        )
    else:
        path_ = fedit.file_path

    if not IS_IN_DOCKER:
        if not os.path.exists(path_):
            raise Exception(f"Error: file {path_} does not exist")

        with open(path_) as f:
            apply_diff_to = f.read()
    else:
        # Copy from docker
        with TemporaryDirectory() as tmpdir:
            rcode = os.system(f"docker cp {IS_IN_DOCKER}:{path_} {tmpdir}")
            if rcode != 0:
                raise Exception(f"Error: Read failed with code {rcode}")
            path_tmp = os.path.join(tmpdir, os.path.basename(path_))
            with open(path_tmp, "r") as f:
                apply_diff_to = f.read()

    fedit.file_edit_using_search_replace_blocks = (
        fedit.file_edit_using_search_replace_blocks.strip()
    )
    lines = fedit.file_edit_using_search_replace_blocks.split("\n")

    if not lines or not re.match(r"^<<<<<<+\s*SEARCH\s*$", lines[0]):
        raise Exception(
            "Error: first line should be `<<<<<< SEARCH` to start a search-replace block"
        )

    n_lines = len(lines)
    i = 0
    replacement_count = 0
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
            console.log("=======")
            for line in replace_block:
                console.log("< " + line)
            console.log("\n\n\n\n")
            search_block_ = "\n".join(search_block)
            replace_block_ = "\n".join(replace_block)

            apply_diff_to = edit_content(apply_diff_to, search_block_, replace_block_)
            replacement_count += 1
        else:
            i += 1

    if replacement_count == 0:
        raise Exception(
            "Error: no valid search-replace blocks found, please check your syntax for FileEdit"
        )

    if not IS_IN_DOCKER:
        with open(path_, "w") as f:
            f.write(apply_diff_to)
    else:
        with TemporaryDirectory() as tmpdir:
            path_tmp = os.path.join(tmpdir, os.path.basename(path_))
            with open(path_tmp, "w") as f:
                f.write(apply_diff_to)
            os.chmod(path_tmp, 0o777)
            # Copy to docker using docker cp
            rcode = os.system(f"docker cp {path_tmp} {IS_IN_DOCKER}:{path_}")
            if rcode != 0:
                raise Exception(f"Error: Write failed with code {rcode}")

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
    | CreateFileNew
    | FileEditFindReplace
    | FileEdit
    | AIAssistant
    | DoneFlag
    | ReadImage
    | ReadFile
    | Initialize
    | Mouse
    | Keyboard
    | ScreenShot
    | GetScreenInfo
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
    elif name == "CreateFileNew":
        return CreateFileNew
    elif name == "FileEditFindReplace":
        return FileEditFindReplace
    elif name == "FileEdit":
        return FileEdit
    elif name == "AIAssistant":
        return AIAssistant
    elif name == "DoneFlag":
        return DoneFlag
    elif name == "ReadImage":
        return ReadImage
    elif name == "ReadFile":
        return ReadFile
    elif name == "Initialize":
        return Initialize
    elif name == "Mouse":
        return Mouse
    elif name == "Keyboard":
        return Keyboard
    elif name == "ScreenShot":
        return ScreenShot
    elif name == "GetScreenInfo":
        return GetScreenInfo
    else:
        raise ValueError(f"Unknown tool name: {name}")


def get_tool_output(
    args: dict[object, object]
    | Confirmation
    | BashCommand
    | BashInteraction
    | ResetShell
    | CreateFileNew
    | FileEditFindReplace
    | FileEdit
    | AIAssistant
    | DoneFlag
    | ReadImage
    | Initialize
    | ReadFile
    | Mouse
    | Keyboard
    | ScreenShot
    | GetScreenInfo,
    enc: tiktoken.Encoding,
    limit: float,
    loop_call: Callable[[str, float], tuple[str, float]],
    max_tokens: Optional[int],
) -> tuple[list[str | ImageData | DoneFlag], float]:
    global IS_IN_DOCKER
    if isinstance(args, dict):
        adapter = TypeAdapter[
            Confirmation
            | BashCommand
            | BashInteraction
            | ResetShell
            | CreateFileNew
            | FileEditFindReplace
            | FileEdit
            | AIAssistant
            | DoneFlag
            | ReadImage
            | ReadFile
            | Initialize
            | Mouse
            | Keyboard
            | ScreenShot
            | GetScreenInfo,
        ](
            Confirmation
            | BashCommand
            | BashInteraction
            | ResetShell
            | CreateFileNew
            | FileEditFindReplace
            | FileEdit
            | AIAssistant
            | DoneFlag
            | ReadImage
            | ReadFile
            | Initialize
            | Mouse
            | Keyboard
            | ScreenShot
            | GetScreenInfo
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
        output = execute_bash(enc, arg, max_tokens, None)
    elif isinstance(arg, CreateFileNew):
        console.print("Calling write file tool")
        output = write_file(arg, True), 0
    elif isinstance(arg, FileEdit):
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
    elif isinstance(arg, ReadFile):
        console.print("Calling read file tool")
        output = read_file(arg, max_tokens), 0.0
    elif isinstance(arg, ResetShell):
        console.print("Calling reset shell tool")
        output = reset_shell(), 0.0
    elif isinstance(arg, Initialize):
        console.print("Calling initial info tool")
        output = initial_info(), 0.0
    elif isinstance(arg, (Mouse, Keyboard, ScreenShot, GetScreenInfo)):
        console.print(f"Calling {type(arg).__name__} tool")
        outputs_cost = run_computer_tool(arg), 0.0
        console.print(outputs_cost[0][0])
        outputs: list[ImageData | str | DoneFlag] = [outputs_cost[0][0]]
        imgBs64 = outputs_cost[0][1]
        if imgBs64:
            console.print("Captured screenshot")
            outputs.append(ImageData(media_type="image/png", data=imgBs64))
            if not IS_IN_DOCKER and isinstance(arg, GetScreenInfo):
                try:
                    # At this point we should go into the docker env
                    res, _ = execute_bash(
                        enc,
                        BashCommand(
                            command=f"docker exec -it {arg.docker_image_id} sh"
                        ),
                        None,
                        0.2,
                    )
                    # At this point we should go into the docker env
                    res, _ = execute_bash(
                        enc,
                        BashInteraction(
                            send_text=f"export PS1={PROMPT}", type="BashInteraction"
                        ),
                        None,
                        0.2,
                    )
                    # Do chown of home dir
                except Exception as e:
                    reset_shell()
                    raise Exception(
                        f"Some error happened while going inside docker. I've reset the shell. Please start again. Error {e}"
                    )
                IS_IN_DOCKER = arg.docker_image_id
        return outputs, outputs_cost[1]
    else:
        raise ValueError(f"Unknown tool: {arg}")
    if isinstance(output[0], str):
        console.print(str(output[0]))
    else:
        console.print(f"Received {type(output[0])} from tool")
    return [output[0]], output[1]


History = list[ChatCompletionMessageParam]

default_enc = tiktoken.encoding_for_model("gpt-4o")
default_model: Models = "gpt-4o-2024-08-06"
default_cost = CostData(cost_per_1m_input_tokens=0.15, cost_per_1m_output_tokens=0.6)
curr_cost = 0.0


class Mdata(BaseModel):
    data: (
        BashCommand
        | BashInteraction
        | CreateFileNew
        | ResetShell
        | FileEditFindReplace
        | FileEdit
        | str
        | ReadFile
        | Initialize
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
                    outputs, cost = get_tool_output(
                        mdata.data, default_enc, 0.0, lambda x, y: ("", 0), 8000
                    )
                    output = outputs[0]
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


def read_file(readfile: ReadFile, max_tokens: Optional[int]) -> str:
    console.print(f"Reading file: {readfile.file_path}")

    if not os.path.isabs(readfile.file_path):
        return f"Failure: file_path should be absolute path, current working directory is {CWD}"

    if not IS_IN_DOCKER:
        path = Path(readfile.file_path)
        if not path.exists():
            return f"Error: file {readfile.file_path} does not exist"

        with path.open("r") as f:
            content = f.read()

    else:
        return_code, content, stderr = command_run(
            f"cat {readfile.file_path}", timeout=TIMEOUT
        )
        if return_code != 0:
            raise Exception(
                f"Error: cat {readfile.file_path} failed with code {return_code}\nstdout: {content}\nstderr: {stderr}"
            )

    if max_tokens is not None:
        tokens = default_enc.encode(content)
        if len(tokens) > max_tokens:
            content = default_enc.decode(tokens[: max_tokens - 5])
            content += "\n...(truncated)"

    return content
