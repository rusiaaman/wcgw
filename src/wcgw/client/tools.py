import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import re
import shlex
import sys
import threading
import importlib.metadata
import time
import traceback
from tempfile import NamedTemporaryFile, TemporaryDirectory
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
import humanize
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

from syntax_checker import check_syntax
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ParsedChatCompletionMessage,
)
from difflib import SequenceMatcher

from ..types_ import (
    BashCommand,
    BashInteraction,
    WriteIfEmpty,
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


class DisableConsole:
    def print(self, *args, **kwargs):  # type: ignore
        pass

    def log(self, *args, **kwargs):  # type: ignore
        pass


console: rich.console.Console | DisableConsole = rich.console.Console(
    style="magenta", highlight=False, markup=False
)

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
    try:
        shell = pexpect.spawn(
            "/bin/bash",
            env={**os.environ, **{"PS1": PROMPT}},  # type: ignore[arg-type]
            echo=False,
            encoding="utf-8",
            timeout=TIMEOUT,
        )
        shell.sendline(f"export PS1={PROMPT}")
    except Exception as e:
        console.print(traceback.format_exc())
        console.log(f"Error starting shell: {e}. Retrying without rc ...")

        shell = pexpect.spawn(
            "/bin/bash --noprofile --norc",
            env={**os.environ, **{"PS1": PROMPT}},  # type: ignore[arg-type]
            echo=False,
            encoding="utf-8",
            timeout=TIMEOUT,
        )

    shell.expect(PROMPT, timeout=TIMEOUT)
    shell.sendline("stty -icanon -echo")
    shell.expect(PROMPT, timeout=TIMEOUT)
    return shell


def _is_int(mystr: str) -> bool:
    try:
        int(mystr)
        return True
    except ValueError:
        return False


def _get_exit_code(shell: pexpect.spawn) -> int:  # type: ignore
    if PROMPT != PROMPT_CONST:
        return 0
    # First reset the prompt in case venv was sourced or other reasons.
    shell.sendline(f"export PS1={PROMPT}")
    shell.expect(PROMPT, timeout=0.2)
    # Reset echo also if it was enabled
    shell.sendline("stty -icanon -echo")
    shell.expect(PROMPT, timeout=0.2)
    shell.sendline("echo $?")
    before = ""
    while not _is_int(before):  # Consume all previous output
        try:
            shell.expect(PROMPT, timeout=0.2)
        except pexpect.TIMEOUT:
            console.print(f"Couldn't get exit code, before: {before}")
            raise
        assert isinstance(shell.before, str)
        # Render because there could be some anscii escape sequences still set like in google colab env
        before = render_terminal_output(shell.before).strip()

    try:
        return int((before))
    except ValueError:
        raise ValueError(f"Malformed output: {before}")


BASH_CLF_OUTPUT = Literal["repl", "pending"]


class BashState:
    def __init__(self) -> None:
        self._init()

    def _init(self) -> None:
        self._state: Literal["repl"] | datetime.datetime = "repl"
        self._is_in_docker: Optional[str] = ""
        self._cwd: str = os.getcwd()
        self._shell = start_shell()
        self._whitelist_for_overwrite: set[str] = set()

        # Get exit info to ensure shell is ready
        _get_exit_code(self._shell)

    @property
    def shell(self) -> pexpect.spawn:  # type: ignore
        return self._shell

    def set_pending(self) -> None:
        if not isinstance(self._state, datetime.datetime):
            self._state = datetime.datetime.now()

    def set_repl(self) -> None:
        self._state = "repl"

    @property
    def state(self) -> BASH_CLF_OUTPUT:
        if self._state == "repl":
            return "repl"
        return "pending"

    @property
    def is_in_docker(self) -> Optional[str]:
        return self._is_in_docker

    def set_in_docker(self, docker_image_id: str) -> None:
        self._is_in_docker = docker_image_id

    @property
    def cwd(self) -> str:
        return self._cwd

    def update_cwd(self) -> str:
        BASH_STATE.shell.sendline("pwd")
        BASH_STATE.shell.expect(PROMPT, timeout=0.2)
        assert isinstance(BASH_STATE.shell.before, str)
        current_dir = render_terminal_output(BASH_STATE.shell.before).strip()
        self._cwd = current_dir
        return current_dir

    def reset(self) -> None:
        self.shell.close(True)
        self._init()

    def get_pending_for(self) -> str:
        if isinstance(self._state, datetime.datetime):
            timedelta = datetime.datetime.now() - self._state
            return humanize.naturaldelta(
                timedelta + datetime.timedelta(seconds=TIMEOUT)
            )
        return "Not pending"

    @property
    def whitelist_for_overwrite(self) -> set[str]:
        return self._whitelist_for_overwrite

    def add_to_whitelist_for_overwrite(self, file_path: str) -> None:
        self._whitelist_for_overwrite.add(file_path)


BASH_STATE = BashState()


def initial_info() -> str:
    uname_sysname = os.uname().sysname
    uname_machine = os.uname().machine
    return f"""
System: {uname_sysname}
Machine: {uname_machine}
Current working directory: {BASH_STATE.cwd}
wcgw version: {importlib.metadata.version("wcgw")}
"""


def reset_shell() -> str:
    BASH_STATE.reset()
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
        BASH_STATE.shell.sendintr()
        index = BASH_STATE.shell.expect([PROMPT, pexpect.TIMEOUT], timeout=0.2)
        if index == 0:
            return True
        before = BASH_STATE.shell.before or ""
        assert before, "Something went wrong updating repl prompt"
        PROMPT = before.split("\n")[-1].strip()
        # Escape all regex
        PROMPT = re.escape(PROMPT)
        console.print(f"Trying to update prompt to: {PROMPT.encode()!r}")
        index = 0
        while index == 0:
            # Consume all REPL prompts till now
            index = BASH_STATE.shell.expect([PROMPT, pexpect.TIMEOUT], timeout=0.2)
        console.print(f"Prompt updated to: {PROMPT}")
        return True
    return False


def get_status() -> str:
    exit_code: Optional[int] = None

    status = "\n\n---\n\n"
    if BASH_STATE.state == "pending":
        status += "status = still running\n"
        status += "running for = " + BASH_STATE.get_pending_for() + "\n"
        status += "cwd = " + BASH_STATE.cwd + "\n"
    else:
        exit_code = _get_exit_code(BASH_STATE.shell)
        status += f"status = exited with code {exit_code}\n"
        status += "cwd = " + BASH_STATE.update_cwd() + "\n"

    return status.rstrip()


T = TypeVar("T")


def save_out_of_context(
    tokens: list[T],
    max_tokens: int,
    suffix: str,
    tokens_converted: Callable[[list[T]], str],
) -> tuple[str, list[Path]]:
    file_contents = list[str]()
    for i in range(0, len(tokens), max_tokens):
        file_contents.append(tokens_converted(tokens[i : i + max_tokens]))

    if len(file_contents) == 1:
        return file_contents[0], []

    rest_paths = list[Path]()
    for i, content in enumerate(file_contents):
        if i == 0:
            continue
        file_path = NamedTemporaryFile(delete=False, suffix=suffix).name
        with open(file_path, "w") as f:
            f.write(content)
        rest_paths.append(Path(file_path))

    return file_contents[0], rest_paths


def execute_bash(
    enc: tiktoken.Encoding,
    bash_arg: BashCommand | BashInteraction,
    max_tokens: Optional[int],
    timeout_s: Optional[float],
) -> tuple[str, float]:
    try:
        is_interrupt = False
        if isinstance(bash_arg, BashCommand):
            updated_repl_mode = update_repl_prompt(bash_arg.command)
            if updated_repl_mode:
                BASH_STATE.set_repl()
                response = (
                    "Prompt updated, you can execute REPL lines using BashCommand now"
                )
                console.print(response)
                return (
                    response,
                    0,
                )

            console.print(f"$ {bash_arg.command}")
            if BASH_STATE.state == "pending":
                raise ValueError(WAITING_INPUT_MESSAGE)
            command = bash_arg.command.strip()

            if "\n" in command:
                raise ValueError(
                    "Command should not contain newline character in middle. Run only one command at a time."
                )

            BASH_STATE.shell.sendline(command)

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
                        BASH_STATE.shell.send("\033[A")
                    elif char == "Key-down":
                        BASH_STATE.shell.send("\033[B")
                    elif char == "Key-left":
                        BASH_STATE.shell.send("\033[D")
                    elif char == "Key-right":
                        BASH_STATE.shell.send("\033[C")
                    elif char == "Enter":
                        BASH_STATE.shell.send("\n")
                    elif char == "Ctrl-c":
                        BASH_STATE.shell.sendintr()
                        is_interrupt = True
                    elif char == "Ctrl-d":
                        BASH_STATE.shell.sendintr()
                        is_interrupt = True
                    elif char == "Ctrl-z":
                        BASH_STATE.shell.send("\x1a")
                    else:
                        raise Exception(f"Unknown special character: {char}")
            elif bash_arg.send_ascii:
                console.print(f"Sending ASCII sequence: {bash_arg.send_ascii}")
                for ascii_char in bash_arg.send_ascii:
                    BASH_STATE.shell.send(chr(ascii_char))
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
                    BASH_STATE.set_repl()
                    response = "Prompt updated, you can execute REPL lines using BashCommand now"
                    console.print(response)
                    return (
                        response,
                        0,
                    )
                console.print(f"Interact text: {bash_arg.send_text}")
                BASH_STATE.shell.sendline(bash_arg.send_text)

    except KeyboardInterrupt:
        BASH_STATE.shell.sendintr()
        BASH_STATE.shell.expect(PROMPT)
        return "---\n\nFailure: user interrupted the execution", 0.0

    wait = timeout_s or TIMEOUT
    index = BASH_STATE.shell.expect([PROMPT, pexpect.TIMEOUT], timeout=wait)
    if index == 1:
        BASH_STATE.set_pending()
        text = BASH_STATE.shell.before or ""

        text = render_terminal_output(text[-100_000:])
        tokens = enc.encode(text)

        if max_tokens and len(tokens) >= max_tokens:
            text = "(...truncated)\n" + enc.decode(tokens[-(max_tokens - 1) :])

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

    BASH_STATE.set_repl()

    if is_interrupt:
        return "Interrupt successful", 0.0

    assert isinstance(BASH_STATE.shell.before, str)
    output = render_terminal_output(BASH_STATE.shell.before)

    tokens = enc.encode(output)
    if max_tokens and len(tokens) >= max_tokens:
        output = "(...truncated)\n" + enc.decode(tokens[-(max_tokens - 1) :])

    try:
        exit_status = get_status()
        output += exit_status
    except ValueError as e:
        console.print(output)
        console.print(traceback.format_exc())
        console.print("Malformed output, restarting shell", style="red")
        # Malformed output, restart shell
        BASH_STATE.reset()
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
            console.print(f"Connection closed for UUID: {client_uuid}, retrying")
            serve_image_in_bg(file_path, client_uuid, name)


MEDIA_TYPES = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]


class ImageData(BaseModel):
    media_type: MEDIA_TYPES
    data: str

    @property
    def dataurl(self) -> str:
        return f"data:{self.media_type};base64," + self.data


Param = ParamSpec("Param")


def ensure_no_previous_output(func: Callable[Param, T]) -> Callable[Param, T]:
    def wrapper(*args: Param.args, **kwargs: Param.kwargs) -> T:
        if BASH_STATE.state == "pending":
            raise ValueError(WAITING_INPUT_MESSAGE)

        return func(*args, **kwargs)

    return wrapper


def read_image_from_shell(file_path: str) -> ImageData:
    if not os.path.isabs(file_path):
        file_path = os.path.join(BASH_STATE.cwd, file_path)

    if not BASH_STATE.is_in_docker:
        if not os.path.exists(file_path):
            raise ValueError(f"File {file_path} does not exist")

        with open(file_path, "rb") as image_file:
            image_bytes = image_file.read()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            image_type = mimetypes.guess_type(file_path)[0]
            return ImageData(media_type=image_type, data=image_b64)  # type: ignore
    else:
        with TemporaryDirectory() as tmpdir:
            rcode = os.system(
                f"docker cp {BASH_STATE.is_in_docker}:{shlex.quote(file_path)} {tmpdir}"
            )
            if rcode != 0:
                raise Exception(f"Error: Read failed with code {rcode}")
            path_ = os.path.join(tmpdir, os.path.basename(file_path))
            with open(path_, "rb") as f:
                image_bytes = f.read()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            image_type = mimetypes.guess_type(file_path)[0]
            return ImageData(media_type=image_type, data=image_b64)  # type: ignore


def write_file(writefile: WriteIfEmpty, error_on_exist: bool) -> str:
    if not os.path.isabs(writefile.file_path):
        return f"Failure: file_path should be absolute path, current working directory is {BASH_STATE.cwd}"
    else:
        path_ = writefile.file_path

    error_on_exist_ = error_on_exist and path_ not in BASH_STATE.whitelist_for_overwrite
    add_overwrite_warning = ""
    if not BASH_STATE.is_in_docker:
        if (error_on_exist or error_on_exist_) and os.path.exists(path_):
            content = Path(path_).read_text().strip()
            if content:
                if error_on_exist_:
                    return f"Error: can't write to existing file {path_}, use other functions to edit the file"
                elif error_on_exist:
                    add_overwrite_warning = content

        # Since we've already errored once, add this to whitelist
        BASH_STATE.add_to_whitelist_for_overwrite(path_)

        path = Path(path_)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with path.open("w") as f:
                f.write(writefile.file_content)
        except OSError as e:
            return f"Error: {e}"
    else:
        if error_on_exist or error_on_exist_:
            return_code, content, stderr = command_run(
                f"docker exec {BASH_STATE.is_in_docker} cat {shlex.quote(path_)}",
                timeout=TIMEOUT,
            )
            if return_code != 0 and content.strip():
                if error_on_exist_:
                    return f"Error: can't write to existing file {path_}, use other functions to edit the file"
                else:
                    add_overwrite_warning = content

        # Since we've already errored once, add this to whitelist
        BASH_STATE.add_to_whitelist_for_overwrite(path_)

        with TemporaryDirectory() as tmpdir:
            tmppath = os.path.join(tmpdir, os.path.basename(path_))
            with open(tmppath, "w") as f:
                f.write(writefile.file_content)
            os.chmod(tmppath, 0o777)
            parent_dir = os.path.dirname(path_)
            rcode = os.system(
                f"docker exec {BASH_STATE.is_in_docker} mkdir -p {parent_dir}"
            )
            if rcode != 0:
                return f"Error: Write failed with code while creating dirs {rcode}"

            rcode = os.system(
                f"docker cp {shlex.quote(tmppath)} {BASH_STATE.is_in_docker}:{shlex.quote(path_)}"
            )
            if rcode != 0:
                return f"Error: Write failed with code {rcode}"

    extension = Path(path_).suffix.lstrip(".")

    console.print(f"File written to {path_}")

    warnings = []
    try:
        check = check_syntax(extension, writefile.file_content)
        syntax_errors = check.description
        if syntax_errors:
            console.print(f"W: Syntax errors encountered: {syntax_errors}")
            warnings.append(f"""
---
Warning: tree-sitter reported syntax errors, please re-read the file and fix if any errors. 
Errors:
{syntax_errors}
---
            """)

    except Exception:
        pass

    if add_overwrite_warning:
        warnings.append(
            "\n---\nWarning: a file already existed and it's now overwritten. Was it a mistake? If yes please revert your action."
            "Here's the previous content:\n```\n" + add_overwrite_warning + "\n```"
            "\n---\n"
        )

    return "Success" + "".join(warnings)


def find_least_edit_distance_substring(
    orig_content_lines: list[str], find_lines: list[str]
) -> tuple[list[str], str]:
    # Prepare content lines, stripping whitespace and keeping track of original indices
    content_lines = [line.strip() for line in orig_content_lines]
    new_to_original_indices = {}
    new_content_lines = []
    for i, line in enumerate(content_lines):
        if not line:
            continue
        new_content_lines.append(line)
        new_to_original_indices[len(new_content_lines) - 1] = i
    content_lines = new_content_lines

    # Prepare find lines, removing empty lines
    find_lines = [line.strip() for line in find_lines if line.strip()]

    # Initialize variables for best match tracking
    max_similarity = 0.0
    min_edit_distance_lines = []
    context_lines = []

    # For each possible starting position in content
    for i in range(max(1, len(content_lines) - len(find_lines) + 1)):
        # Calculate similarity for the block starting at position i
        block_similarity = 0.0
        for j in range(len(find_lines)):
            if (i + j) < len(content_lines):
                # Use SequenceMatcher for more efficient similarity calculation
                similarity = SequenceMatcher(
                    None, content_lines[i + j], find_lines[j]
                ).ratio()
                block_similarity += similarity

        # If this block is more similar than previous best
        if block_similarity > max_similarity:
            max_similarity = block_similarity
            # Map back to original line indices
            orig_start_index = new_to_original_indices[i]
            orig_end_index = (
                new_to_original_indices.get(
                    i + len(find_lines) - 1, len(orig_content_lines) - 1
                )
                + 1
            )
            # Get the original lines
            min_edit_distance_lines = orig_content_lines[
                orig_start_index:orig_end_index
            ]
            # Get context (10 lines before and after)
            context_lines = orig_content_lines[
                max(0, orig_start_index - 10) : (orig_end_index + 10)
            ]

    return (
        min_edit_distance_lines,
        "\n".join(context_lines),
    )


def lines_replacer(
    orig_content_lines: list[str], search_lines: list[str], replace_lines: list[str]
) -> str:
    # Validation for empty search
    search_lines = list(filter(None, [x.strip() for x in search_lines]))

    # Create mapping of non-empty lines to original indices
    new_to_original_indices = []
    new_content_lines = []
    for i, line in enumerate(orig_content_lines):
        stripped = line.strip()
        if not stripped:
            continue
        new_content_lines.append(stripped)
        new_to_original_indices.append(i)

    if not new_content_lines and not search_lines:
        return "\n".join(replace_lines)
    elif not search_lines:
        raise ValueError("Search block is empty")
    elif not new_content_lines:
        raise ValueError("File content is empty")

    # Search for matching block
    for i in range(len(new_content_lines) - len(search_lines) + 1):
        if all(
            new_content_lines[i + j] == search_lines[j]
            for j in range(len(search_lines))
        ):
            start_idx = new_to_original_indices[i]
            end_idx = new_to_original_indices[i + len(search_lines) - 1] + 1
            return "\n".join(
                orig_content_lines[:start_idx]
                + replace_lines
                + orig_content_lines[end_idx:]
            )

    raise ValueError("Search block not found in content")


def edit_content(content: str, find_lines: str, replace_with_lines: str) -> str:
    replace_with_lines_ = replace_with_lines.split("\n")
    find_lines_ = find_lines.split("\n")
    content_lines_ = content.split("\n")
    try:
        return lines_replacer(content_lines_, find_lines_, replace_with_lines_)
    except ValueError:
        pass

    _, context_lines = find_least_edit_distance_substring(content_lines_, find_lines_)

    raise Exception(
        f"""Error: no match found for the provided search block.
            Requested search block: \n```\n{find_lines}\n```
            Possible relevant section in the file:\n---\n```\n{context_lines}\n```\n---\nFile not edited
        \nPlease retry with exact search. Re-read the file if unsure.
        """
    )


def do_diff_edit(fedit: FileEdit) -> str:
    try:
        return _do_diff_edit(fedit)
    except Exception as e:
        # Try replacing \"
        try:
            fedit = FileEdit(
                file_path=fedit.file_path,
                file_edit_using_search_replace_blocks=fedit.file_edit_using_search_replace_blocks.replace(
                    '\\"', '"'
                ),
            )
            return _do_diff_edit(fedit)
        except Exception:
            pass
        raise e


def _do_diff_edit(fedit: FileEdit) -> str:
    console.log(f"Editing file: {fedit.file_path}")

    if not os.path.isabs(fedit.file_path):
        raise Exception(
            f"Failure: file_path should be absolute path, current working directory is {BASH_STATE.cwd}"
        )
    else:
        path_ = fedit.file_path

    # The LLM is now aware that the file exists
    BASH_STATE.add_to_whitelist_for_overwrite(path_)

    if not BASH_STATE.is_in_docker:
        if not os.path.exists(path_):
            raise Exception(f"Error: file {path_} does not exist")

        with open(path_) as f:
            apply_diff_to = f.read()
    else:
        # Copy from docker
        with TemporaryDirectory() as tmpdir:
            rcode = os.system(
                f"docker cp {BASH_STATE.is_in_docker}:{shlex.quote(path_)} {tmpdir}"
            )
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

    if not BASH_STATE.is_in_docker:
        with open(path_, "w") as f:
            f.write(apply_diff_to)
    else:
        with TemporaryDirectory() as tmpdir:
            path_tmp = os.path.join(tmpdir, os.path.basename(path_))
            with open(path_tmp, "w") as f:
                f.write(apply_diff_to)
            os.chmod(path_tmp, 0o777)
            # Copy to docker using docker cp
            rcode = os.system(
                f"docker cp {shlex.quote(path_tmp)} {BASH_STATE.is_in_docker}:{shlex.quote(path_)}"
            )
            if rcode != 0:
                raise Exception(f"Error: Write failed with code {rcode}")

    syntax_errors = ""
    extension = Path(path_).suffix.lstrip(".")
    try:
        check = check_syntax(extension, apply_diff_to)
        syntax_errors = check.description
        if syntax_errors:
            console.print(f"W: Syntax errors encountered: {syntax_errors}")
            return f"""Wrote file succesfully.
---
However, tree-sitter reported syntax errors, please re-read the file and fix if there are any errors.
Errors:
{syntax_errors}
            """
    except Exception:
        pass

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
    | WriteIfEmpty
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
    elif name == "WriteIfEmpty":
        return WriteIfEmpty
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


TOOL_CALLS: list[TOOLS] = []


def get_tool_output(
    args: dict[object, object] | TOOLS,
    enc: tiktoken.Encoding,
    limit: float,
    loop_call: Callable[[str, float], tuple[str, float]],
    max_tokens: Optional[int],
) -> tuple[list[str | ImageData | DoneFlag], float]:
    global IS_IN_DOCKER, TOOL_CALLS
    if isinstance(args, dict):
        adapter = TypeAdapter[TOOLS](TOOLS)
        arg = adapter.validate_python(args)
    else:
        arg = args
    output: tuple[str | DoneFlag | ImageData, float]
    TOOL_CALLS.append(arg)
    if isinstance(arg, Confirmation):
        console.print("Calling ask confirmation tool")
        output = ask_confirmation(arg), 0.0
    elif isinstance(arg, (BashCommand | BashInteraction)):
        console.print("Calling execute bash tool")
        output = execute_bash(enc, arg, max_tokens, arg.wait_for_seconds)
    elif isinstance(arg, WriteIfEmpty):
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
        # First force reset
        reset_shell()
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
            if not BASH_STATE.is_in_docker and isinstance(arg, GetScreenInfo):
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
                BASH_STATE.set_in_docker(arg.docker_image_id)
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
        | WriteIfEmpty
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

            print(f"Connected. Share this user id with the chatbot: {client_uuid}")
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
                    console.print(traceback.format_exc())
                assert isinstance(output, str)
                websocket.send(output)

    except (websockets.ConnectionClosed, ConnectionError, OSError):
        print(f"Connection closed for UUID: {client_uuid}, retrying")
        time.sleep(0.5)
        register_client(server_url, client_uuid)


run = Typer(pretty_exceptions_show_locals=False, no_args_is_help=True)


@run.command()
def app(
    server_url: str = "",
    client_uuid: Optional[str] = None,
    version: bool = typer.Option(False, "--version", "-v"),
) -> None:
    if version:
        version_ = importlib.metadata.version("wcgw")
        print(f"wcgw version: {version_}")
        exit()
    if not server_url:
        server_url = os.environ.get("WCGW_RELAY_SERVER", "")
        if not server_url:
            print(
                "Error: Please provide relay server url using --server_url or WCGW_RELAY_SERVER environment variable"
            )
            print(
                "\tNOTE: you need to run a relay server first, author doesn't host a relay server anymore."
            )
            print("\thttps://github.com/rusiaaman/wcgw/blob/main/openai.md")
            print("\tExample `--server-url=ws://localhost:8000/v1/register`")
            raise typer.Exit(1)
    register_client(server_url, client_uuid or "")


def read_file(readfile: ReadFile, max_tokens: Optional[int]) -> str:
    console.print(f"Reading file: {readfile.file_path}")

    if not os.path.isabs(readfile.file_path):
        return f"Failure: file_path should be absolute path, current working directory is {BASH_STATE.cwd}"

    BASH_STATE.add_to_whitelist_for_overwrite(readfile.file_path)

    if not BASH_STATE.is_in_docker:
        path = Path(readfile.file_path)
        if not path.exists():
            return f"Error: file {readfile.file_path} does not exist"

        with path.open("r") as f:
            content = f.read()

    else:
        return_code, content, stderr = command_run(
            f"docker exec {BASH_STATE.is_in_docker} cat {shlex.quote(readfile.file_path)}",
            timeout=TIMEOUT,
        )
        if return_code != 0:
            raise Exception(
                f"Error: cat {readfile.file_path} failed with code {return_code}\nstdout: {content}\nstderr: {stderr}"
            )

    if max_tokens is not None:
        tokens = default_enc.encode(content)
        if len(tokens) > max_tokens:
            content, rest = save_out_of_context(
                tokens,
                max_tokens - 100,
                Path(readfile.file_path).suffix,
                default_enc.decode,
            )
            if rest:
                rest_ = "\n".join(map(str, rest))
                content += f"\n(...truncated)\n---\nI've split the rest of the file into multiple files. Here are the remaining splits, please read them:\n{rest_}"

    return content
