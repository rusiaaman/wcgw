import base64
import datetime
import fnmatch
import glob
import importlib.metadata
import json
import mimetypes
import os
import re
import shlex
import time
import traceback
import uuid
from os.path import expanduser
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import (
    Any,
    Callable,
    Literal,
    Optional,
    ParamSpec,
    Type,
    TypeVar,
)

import pexpect
import pyte
import rich
import tokenizers  # type: ignore
import typer
import websockets
from openai.types.chat import (
    ChatCompletionMessageParam,
)
from pydantic import BaseModel, TypeAdapter
from syntax_checker import check_syntax
from typer import Typer
from websockets.sync.client import connect as syncconnect

from ..types_ import (
    BashCommand,
    BashInteraction,
    CodeWriterMode,
    ContextSave,
    FileEdit,
    FileEditFindReplace,
    GetScreenInfo,
    Initialize,
    Keyboard,
    Modes,
    ModesConfig,
    Mouse,
    ReadFiles,
    ReadImage,
    ResetShell,
    ScreenShot,
    WriteIfEmpty,
)
from .computer_use import run_computer_tool
from .file_ops.search_replace import search_replace_edit
from .memory import load_memory, save_memory
from .modes import (
    ARCHITECT_PROMPT,
    WCGW_PROMPT,
    BashCommandMode,
    FileEditMode,
    WriteIfEmptyMode,
    code_writer_prompt,
    modes_to_state,
)
from .repo_ops.repo_context import get_repo_context
from .sys_utils import command_run


class DisableConsole:
    def print(self, *args, **kwargs):  # type: ignore
        pass

    def log(self, *args, **kwargs):  # type: ignore
        pass


console: rich.console.Console | DisableConsole = rich.console.Console(
    style="magenta", highlight=False, markup=False
)

TIMEOUT = 5
TIMEOUT_WHILE_OUTPUT = 20
OUTPUT_WAIT_PATIENCE = 3


def render_terminal_output(text: str) -> list[str]:
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
    return lines


def get_incremental_output(old_output: list[str], new_output: list[str]) -> list[str]:
    nold = len(old_output)
    nnew = len(new_output)
    if not old_output:
        return new_output
    for i in range(nnew - 1, -1, -1):
        if new_output[i] != old_output[-1]:
            continue
        for j in range(i - 1, -1, -1):
            if (nold - 1 + j - i) < 0:
                break
            if new_output[j] != old_output[-1 + j - i]:
                break
        else:
            return new_output[i + 1 :]
    return new_output


class Confirmation(BaseModel):
    prompt: str


def ask_confirmation(prompt: Confirmation) -> str:
    response = input(prompt.prompt + " [y/n] ")
    return "Yes" if response.lower() == "y" else "No"


PROMPT_CONST = "#@wcgw@#"
PROMPT = PROMPT_CONST


def start_shell(is_restricted_mode: bool, initial_dir: str) -> pexpect.spawn:  # type: ignore
    cmd = "/bin/bash"
    if is_restricted_mode:
        cmd += " -r"

    try:
        shell = pexpect.spawn(
            cmd,
            env={**os.environ, **{"PS1": PROMPT}},  # type: ignore[arg-type]
            echo=False,
            encoding="utf-8",
            timeout=TIMEOUT,
            cwd=initial_dir,
        )
        shell.sendline(
            f"export PROMPT_COMMAND= PS1={PROMPT}"
        )  # Unset prompt command to avoid interfering
        shell.expect(PROMPT, timeout=TIMEOUT)
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
        shell.sendline(f"export PS1={PROMPT}")
        shell.expect(PROMPT, timeout=TIMEOUT)

    shell.sendline("stty -icanon -echo")
    shell.expect(PROMPT, timeout=TIMEOUT)
    shell.sendline("set +o pipefail")
    shell.expect(PROMPT, timeout=TIMEOUT)
    shell.sendline("export GIT_PAGER=cat PAGER=cat")
    shell.expect(PROMPT, timeout=TIMEOUT)
    return shell


def _is_int(mystr: str) -> bool:
    try:
        int(mystr)
        return True
    except ValueError:
        return False


def _ensure_env_and_bg_jobs(shell: pexpect.spawn) -> Optional[int]:  # type: ignore
    if PROMPT != PROMPT_CONST:
        return None
    # First reset the prompt in case venv was sourced or other reasons.
    shell.sendline(f"export PS1={PROMPT}")
    shell.expect(PROMPT, timeout=0.2)
    # Reset echo also if it was enabled
    shell.sendline("stty -icanon -echo")
    shell.expect(PROMPT, timeout=0.2)
    shell.sendline("set +o pipefail")
    shell.expect(PROMPT, timeout=0.2)
    shell.sendline("export GIT_PAGER=cat PAGER=cat")
    shell.expect(PROMPT, timeout=0.2)
    shell.sendline("jobs | wc -l")
    before = ""

    while not _is_int(before):  # Consume all previous output
        try:
            shell.expect(PROMPT, timeout=0.2)
        except pexpect.TIMEOUT:
            console.print(f"Couldn't get exit code, before: {before}")
            raise

        before_val = shell.before
        if not isinstance(before_val, str):
            before_val = str(before_val)
        assert isinstance(before_val, str)
        before_lines = render_terminal_output(before_val)
        before = "\n".join(before_lines).strip()

    try:
        return int(before)
    except ValueError:
        raise ValueError(f"Malformed output: {before}")


BASH_CLF_OUTPUT = Literal["repl", "pending"]


class BashState:
    def __init__(
        self,
        working_dir: str,
        bash_command_mode: Optional[BashCommandMode],
        file_edit_mode: Optional[FileEditMode],
        write_if_empty_mode: Optional[WriteIfEmptyMode],
        mode: Optional[Modes],
        whitelist_for_overwrite: Optional[set[str]] = None,
    ) -> None:
        self._cwd = working_dir or os.getcwd()
        self._bash_command_mode: BashCommandMode = bash_command_mode or BashCommandMode(
            "normal_mode", "all"
        )
        self._file_edit_mode: FileEditMode = file_edit_mode or FileEditMode("all")
        self._write_if_empty_mode: WriteIfEmptyMode = (
            write_if_empty_mode or WriteIfEmptyMode("all")
        )
        self._mode = mode or Modes.wcgw
        self._whitelist_for_overwrite: set[str] = whitelist_for_overwrite or set()

        self._init_shell()

    @property
    def mode(self) -> Modes:
        return self._mode

    @property
    def bash_command_mode(self) -> BashCommandMode:
        return self._bash_command_mode

    @property
    def file_edit_mode(self) -> FileEditMode:
        return self._file_edit_mode

    @property
    def write_if_empty_mode(self) -> WriteIfEmptyMode:
        return self._write_if_empty_mode

    def _init_shell(self) -> None:
        self._state: Literal["repl"] | datetime.datetime = "repl"
        self._is_in_docker: Optional[str] = ""
        # Ensure self._cwd exists
        os.makedirs(self._cwd, exist_ok=True)
        self._shell = start_shell(
            self._bash_command_mode.bash_mode == "restricted_mode",
            self._cwd,
        )

        self._pending_output = ""

        # Get exit info to ensure shell is ready
        _ensure_env_and_bg_jobs(self._shell)

    @property
    def shell(self) -> pexpect.spawn:  # type: ignore
        return self._shell

    def set_pending(self, last_pending_output: str) -> None:
        if not isinstance(self._state, datetime.datetime):
            self._state = datetime.datetime.now()
        self._pending_output = last_pending_output

    def set_repl(self) -> None:
        self._state = "repl"
        self._pending_output = ""

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
        self.shell.sendline("pwd")
        self.shell.expect(PROMPT, timeout=0.2)
        before_val = self.shell.before
        if not isinstance(before_val, str):
            before_val = str(before_val)
        before_lines = render_terminal_output(before_val)
        current_dir = "\n".join(before_lines).strip()
        self._cwd = current_dir
        return current_dir

    def reset_shell(self) -> None:
        self.shell.close(True)
        self._init_shell()

    def serialize(self) -> dict[str, Any]:
        """Serialize BashState to a dictionary for saving"""
        return {
            "bash_command_mode": self._bash_command_mode.serialize(),
            "file_edit_mode": self._file_edit_mode.serialize(),
            "write_if_empty_mode": self._write_if_empty_mode.serialize(),
            "whitelist_for_overwrite": list(self._whitelist_for_overwrite),
            "mode": self._mode,
        }

    @staticmethod
    def parse_state(
        state: dict[str, Any],
    ) -> tuple[BashCommandMode, FileEditMode, WriteIfEmptyMode, Modes, list[str]]:
        return (
            BashCommandMode.deserialize(state["bash_command_mode"]),
            FileEditMode.deserialize(state["file_edit_mode"]),
            WriteIfEmptyMode.deserialize(state["write_if_empty_mode"]),
            Modes[str(state["mode"])],
            state["whitelist_for_overwrite"],
        )

    def load_state(
        self,
        bash_command_mode: BashCommandMode,
        file_edit_mode: FileEditMode,
        write_if_empty_mode: WriteIfEmptyMode,
        mode: Modes,
        whitelist_for_overwrite: list[str],
        cwd: str,
    ) -> None:
        """Create a new BashState instance from a serialized state dictionary"""
        self._bash_command_mode = bash_command_mode
        self._cwd = cwd or self._cwd
        self._file_edit_mode = file_edit_mode
        self._write_if_empty_mode = write_if_empty_mode
        self._whitelist_for_overwrite = set(whitelist_for_overwrite)
        self._mode = mode
        self.reset_shell()

    def get_pending_for(self) -> str:
        if isinstance(self._state, datetime.datetime):
            timedelta = datetime.datetime.now() - self._state
            return (
                str(
                    int(
                        (
                            timedelta + datetime.timedelta(seconds=TIMEOUT)
                        ).total_seconds()
                    )
                )
                + " seconds"
            )

        return "Not pending"

    @property
    def whitelist_for_overwrite(self) -> set[str]:
        return self._whitelist_for_overwrite

    def add_to_whitelist_for_overwrite(self, file_path: str) -> None:
        self._whitelist_for_overwrite.add(file_path)

    @property
    def pending_output(self) -> str:
        return self._pending_output


BASH_STATE = BashState(os.getcwd(), None, None, None, None)
INITIALIZED = False


def initialize(
    any_workspace_path: str,
    read_files_: list[str],
    task_id_to_resume: str,
    max_tokens: Optional[int],
    mode: ModesConfig,
) -> str:
    global BASH_STATE

    # Expand the workspace path
    any_workspace_path = expand_user(any_workspace_path, None)
    repo_context = ""

    memory = ""
    bash_state = None
    if task_id_to_resume:
        try:
            project_root_path, task_mem, bash_state = load_memory(
                task_id_to_resume,
                max_tokens,
                lambda x: default_enc.encode(x).ids,
                lambda x: default_enc.decode(x),
            )
            memory = "Following is the retrieved task:\n" + task_mem
            if os.path.exists(project_root_path):
                any_workspace_path = project_root_path

        except Exception:
            memory = f'Error: Unable to load task with ID "{task_id_to_resume}" '

    folder_to_start = None
    if any_workspace_path:
        if os.path.exists(any_workspace_path):
            repo_context, folder_to_start = get_repo_context(any_workspace_path, 200)

            repo_context = f"---\n# Workspace structure\n{repo_context}\n---\n"

            # update modes if they're relative
            if isinstance(mode, CodeWriterMode):
                mode.update_relative_globs(any_workspace_path)
            else:
                assert isinstance(mode, str)
        else:
            if os.path.abspath(any_workspace_path):
                os.makedirs(any_workspace_path, exist_ok=True)
                repo_context = f"\nInfo: Workspace path {any_workspace_path} did not exist. I've created it for you.\n"
                folder_to_start = Path(any_workspace_path)
            else:
                repo_context = (
                    f"\nInfo: Workspace path {any_workspace_path} does not exist."
                )
    # Restore bash state if available
    if bash_state is not None:
        try:
            parsed_state = BashState.parse_state(bash_state)
            if mode == "wcgw":
                BASH_STATE.load_state(
                    parsed_state[0],
                    parsed_state[1],
                    parsed_state[2],
                    parsed_state[3],
                    parsed_state[4] + list(BASH_STATE.whitelist_for_overwrite),
                    str(folder_to_start) if folder_to_start else "",
                )
            else:
                state = modes_to_state(mode)
                BASH_STATE.load_state(
                    state[0],
                    state[1],
                    state[2],
                    state[3],
                    parsed_state[4] + list(BASH_STATE.whitelist_for_overwrite),
                    str(folder_to_start) if folder_to_start else "",
                )
        except ValueError:
            console.print(traceback.format_exc())
            console.print("Error: couldn't load bash state")
            pass
    else:
        state = modes_to_state(mode)
        BASH_STATE.load_state(
            state[0],
            state[1],
            state[2],
            state[3],
            list(BASH_STATE.whitelist_for_overwrite),
            str(folder_to_start) if folder_to_start else "",
        )
    del mode

    initial_files_context = ""
    if read_files_:
        if folder_to_start:
            read_files_ = [
                os.path.join(folder_to_start, f) if not os.path.isabs(f) else f
                for f in read_files_
            ]
        initial_files = read_files(read_files_, max_tokens)
        initial_files_context = f"---\n# Requested files\n{initial_files}\n---\n"

    uname_sysname = os.uname().sysname
    uname_machine = os.uname().machine

    mode_prompt = ""
    if BASH_STATE.mode == Modes.code_writer:
        mode_prompt = code_writer_prompt(
            BASH_STATE.file_edit_mode.allowed_globs,
            BASH_STATE.write_if_empty_mode.allowed_globs,
            "all" if BASH_STATE.bash_command_mode.allowed_commands else [],
        )
    elif BASH_STATE.mode == Modes.architect:
        mode_prompt = ARCHITECT_PROMPT
    else:
        mode_prompt = WCGW_PROMPT

    output = f"""
{mode_prompt}

# Environment
System: {uname_sysname}
Machine: {uname_machine}
Initialized in directory (also cwd): {BASH_STATE.cwd}

{repo_context}

{initial_files_context}

---

{memory}
"""

    global INITIALIZED
    INITIALIZED = True

    return output


def reset_shell() -> str:
    BASH_STATE.reset_shell()
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
    status = "\n\n---\n\n"
    if BASH_STATE.state == "pending":
        status += "status = still running\n"
        status += "running for = " + BASH_STATE.get_pending_for() + "\n"
        status += "cwd = " + BASH_STATE.cwd + "\n"
    else:
        bg_jobs = _ensure_env_and_bg_jobs(BASH_STATE.shell)
        bg_desc = ""
        if bg_jobs and bg_jobs > 0:
            bg_desc = f"; {bg_jobs} background jobs running"
        status += "status = process exited" + bg_desc + "\n"
        status += "cwd = " + BASH_STATE.update_cwd() + "\n"

    return status.rstrip()


T = TypeVar("T")


def save_out_of_context(content: str, suffix: str) -> str:
    file_path = NamedTemporaryFile(delete=False, suffix=suffix).name
    with open(file_path, "w") as f:
        f.write(content)
    return file_path


def rstrip(lines: list[str]) -> str:
    return "\n".join([line.rstrip() for line in lines])


def expand_user(path: str, docker_id: Optional[str]) -> str:
    if not path or not path.startswith("~") or docker_id:
        return path
    return expanduser(path)


def _incremental_text(text: str, last_pending_output: str) -> str:
    # text = render_terminal_output(text[-100_000:])
    text = text[-100_000:]

    last_pending_output_rendered_lines = render_terminal_output(last_pending_output)
    last_pending_output_rendered = "\n".join(last_pending_output_rendered_lines)
    last_rendered_lines = last_pending_output_rendered.split("\n")
    if not last_rendered_lines:
        return rstrip(render_terminal_output(text))

    text = text[len(last_pending_output) :]
    old_rendered_applied = render_terminal_output(last_pending_output_rendered + text)
    # True incremental is then
    rendered = get_incremental_output(last_rendered_lines[:-1], old_rendered_applied)

    if not rendered:
        return ""

    if rendered[0] == last_rendered_lines[-1]:
        rendered = rendered[1:]
    return rstrip(rendered)


def is_status_check(arg: BashInteraction | BashCommand) -> bool:
    return isinstance(arg, BashInteraction) and (
        arg.send_specials == ["Enter"] or arg.send_ascii == [10]
    )


def execute_bash(
    enc: tokenizers.Tokenizer,
    bash_arg: BashCommand | BashInteraction,
    max_tokens: Optional[int],
    timeout_s: Optional[float],
) -> tuple[str, float]:
    try:
        is_interrupt = False
        if isinstance(bash_arg, BashCommand):
            if BASH_STATE.bash_command_mode.allowed_commands == "none":
                return "Error: BashCommand not allowed in current mode", 0.0
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

            for i in range(0, len(command), 128):
                BASH_STATE.shell.send(command[i : i + 128])
            BASH_STATE.shell.send(BASH_STATE.shell.linesep)

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
                for i in range(0, len(bash_arg.send_text), 128):
                    BASH_STATE.shell.send(bash_arg.send_text[i : i + 128])
                BASH_STATE.shell.send(BASH_STATE.shell.linesep)

    except KeyboardInterrupt:
        BASH_STATE.shell.sendintr()
        BASH_STATE.shell.expect(PROMPT)
        return "---\n\nFailure: user interrupted the execution", 0.0

    wait = min(timeout_s or TIMEOUT, TIMEOUT_WHILE_OUTPUT)
    index = BASH_STATE.shell.expect([PROMPT, pexpect.TIMEOUT], timeout=wait)
    if index == 1:
        text = BASH_STATE.shell.before or ""
        incremental_text = _incremental_text(text, BASH_STATE.pending_output)

        second_wait_success = False
        if is_status_check(bash_arg):
            # There's some text in BashInteraction mode wait for TIMEOUT_WHILE_OUTPUT
            remaining = TIMEOUT_WHILE_OUTPUT - wait
            patience = OUTPUT_WAIT_PATIENCE
            if not incremental_text:
                patience -= 1
            itext = incremental_text
            while remaining > 0 and patience > 0:
                index = BASH_STATE.shell.expect([PROMPT, pexpect.TIMEOUT], timeout=wait)
                if index == 0:
                    second_wait_success = True
                    break
                else:
                    _itext = BASH_STATE.shell.before or ""
                    _itext = _incremental_text(_itext, BASH_STATE.pending_output)
                    if _itext != itext:
                        patience = 3
                    else:
                        patience -= 1
                    itext = _itext

                remaining = remaining - wait

            if not second_wait_success:
                text = BASH_STATE.shell.before or ""
                incremental_text = _incremental_text(text, BASH_STATE.pending_output)

        if not second_wait_success:
            BASH_STATE.set_pending(text)

            tokens = enc.encode(incremental_text)

            if max_tokens and len(tokens) >= max_tokens:
                incremental_text = "(...truncated)\n" + enc.decode(
                    tokens.ids[-(max_tokens - 1) :]
                )

            if is_interrupt:
                incremental_text = (
                    incremental_text
                    + """---
    ----
    Failure interrupting.
    If any REPL session was previously running or if bashrc was sourced, or if there is issue to other REPL related reasons:
        Run BashCommand: "wcgw_update_prompt()" to reset the PS1 prompt.
    Otherwise, you may want to try Ctrl-c again or program specific exit interactive commands.
    """
                )

            exit_status = get_status()
            incremental_text += exit_status

            return incremental_text, 0

    if not isinstance(BASH_STATE.shell.before, str):
        BASH_STATE.shell.before = str(BASH_STATE.shell.before)

    output = _incremental_text(BASH_STATE.shell.before, BASH_STATE.pending_output)
    BASH_STATE.set_repl()

    tokens = enc.encode(output)
    if max_tokens and len(tokens) >= max_tokens:
        output = "(...truncated)\n" + enc.decode(tokens.ids[-(max_tokens - 1) :])

    try:
        exit_status = get_status()
        output += exit_status
    except ValueError:
        console.print(output)
        console.print(traceback.format_exc())
        console.print("Malformed output, restarting shell", style="red")
        # Malformed output, restart shell
        BASH_STATE.reset_shell()
        output = "(exit shell has restarted)"
    return output, 0


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


def truncate_if_over(content: str, max_tokens: Optional[int]) -> str:
    if max_tokens and max_tokens > 0:
        tokens = default_enc.encode(content)
        n_tokens = len(tokens)
        if n_tokens > max_tokens:
            content = (
                default_enc.decode(tokens.ids[: max(0, max_tokens - 100)])
                + "\n(...truncated)"
            )

    return content


def read_image_from_shell(file_path: str) -> ImageData:
    # Expand the path
    file_path = expand_user(file_path, BASH_STATE.is_in_docker)

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


def get_context_for_errors(
    errors: list[tuple[int, int]], file_content: str, max_tokens: Optional[int]
) -> str:
    file_lines = file_content.split("\n")
    min_line_num = max(0, min([error[0] for error in errors]) - 10)
    max_line_num = min(len(file_lines), max([error[0] for error in errors]) + 10)
    context_lines = file_lines[min_line_num:max_line_num]
    context = "\n".join(context_lines)

    if max_tokens is not None and max_tokens > 0:
        ntokens = len(default_enc.encode(context))
        if ntokens > max_tokens:
            return "Please re-read the file to understand the context"
    return f"Here's relevant snippet from the file where the syntax errors occured:\n```\n{context}\n```"


def write_file(
    writefile: WriteIfEmpty, error_on_exist: bool, max_tokens: Optional[int]
) -> str:
    if not os.path.isabs(writefile.file_path):
        return f"Failure: file_path should be absolute path, current working directory is {BASH_STATE.cwd}"
    else:
        path_ = expand_user(writefile.file_path, BASH_STATE.is_in_docker)

    error_on_exist_ = error_on_exist and path_ not in BASH_STATE.whitelist_for_overwrite

    # Validate using write_if_empty_mode after checking whitelist
    allowed_globs = BASH_STATE.write_if_empty_mode.allowed_globs
    if allowed_globs != "all" and not any(
        fnmatch.fnmatch(path_, pattern) for pattern in allowed_globs
    ):
        return f"Error: updating file {path_} not allowed in current mode. Doesn't match allowed globs: {allowed_globs}"
    add_overwrite_warning = ""
    if not BASH_STATE.is_in_docker:
        if (error_on_exist or error_on_exist_) and os.path.exists(path_):
            content = Path(path_).read_text().strip()
            if content:
                content = truncate_if_over(content, max_tokens)

                if error_on_exist_:
                    return (
                        f"Error: can't write to existing file {path_}, use other functions to edit the file"
                        + f"\nHere's the existing content:\n```\n{content}\n```"
                    )
                else:
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
                content = truncate_if_over(content, max_tokens)

                if error_on_exist_:
                    return (
                        f"Error: can't write to existing file {path_}, use other functions to edit the file"
                        + f"\nHere's the existing content:\n```\n{content}\n```"
                    )
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
            context_for_errors = get_context_for_errors(
                check.errors, writefile.file_content, max_tokens
            )
            console.print(f"W: Syntax errors encountered: {syntax_errors}")
            warnings.append(f"""
---
Warning: tree-sitter reported syntax errors
Syntax errors:
{syntax_errors}

{context_for_errors}
---
            """)

    except Exception:
        pass

    if add_overwrite_warning:
        warnings.append(
            "\n---\nWarning: a file already existed and it's now overwritten. Was it a mistake? If yes please revert your action."
            "\n---\n"
            + "Here's the previous content:\n```\n"
            + add_overwrite_warning
            + "\n```"
        )

    return "Success" + "".join(warnings)


def do_diff_edit(fedit: FileEdit, max_tokens: Optional[int]) -> str:
    try:
        return _do_diff_edit(fedit, max_tokens)
    except Exception as e:
        # Try replacing \"
        try:
            fedit = FileEdit(
                file_path=fedit.file_path,
                file_edit_using_search_replace_blocks=fedit.file_edit_using_search_replace_blocks.replace(
                    '\\"', '"'
                ),
            )
            return _do_diff_edit(fedit, max_tokens)
        except Exception:
            pass
        raise e


def _do_diff_edit(fedit: FileEdit, max_tokens: Optional[int]) -> str:
    console.log(f"Editing file: {fedit.file_path}")

    if not os.path.isabs(fedit.file_path):
        raise Exception(
            f"Failure: file_path should be absolute path, current working directory is {BASH_STATE.cwd}"
        )
    else:
        path_ = expand_user(fedit.file_path, BASH_STATE.is_in_docker)

    # Validate using file_edit_mode
    allowed_globs = BASH_STATE.file_edit_mode.allowed_globs
    if allowed_globs != "all" and not any(
        fnmatch.fnmatch(path_, pattern) for pattern in allowed_globs
    ):
        raise Exception(
            f"Error: updating file {path_} not allowed in current mode. Doesn't match allowed globs: {allowed_globs}"
        )

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

    apply_diff_to, comments = search_replace_edit(lines, apply_diff_to, console.log)

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
            context_for_errors = get_context_for_errors(
                check.errors, apply_diff_to, max_tokens
            )

            console.print(f"W: Syntax errors encountered: {syntax_errors}")
            return f"""{comments}
---
Tree-sitter reported syntax errors, please re-read the file and fix if there are any errors.
Syntax errors:
{syntax_errors}

{context_for_errors}
"""
    except Exception:
        pass

    return comments


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
    | ReadFiles
    | Initialize
    | Mouse
    | Keyboard
    | ScreenShot
    | GetScreenInfo
    | ContextSave
)


def which_tool(args: str) -> TOOLS:
    adapter = TypeAdapter[TOOLS](TOOLS, config={"extra": "forbid"})
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
    elif name == "ReadFiles":
        return ReadFiles
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
    elif name == "ContextSave":
        return ContextSave
    else:
        raise ValueError(f"Unknown tool name: {name}")


TOOL_CALLS: list[TOOLS] = []


def get_tool_output(
    args: dict[object, object] | TOOLS,
    enc: tokenizers.Tokenizer,
    limit: float,
    loop_call: Callable[[str, float], tuple[str, float]],
    max_tokens: Optional[int],
) -> tuple[list[str | ImageData | DoneFlag], float]:
    global IS_IN_DOCKER, TOOL_CALLS, INITIALIZED
    if isinstance(args, dict):
        adapter = TypeAdapter[TOOLS](TOOLS, config={"extra": "forbid"})
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
        if not INITIALIZED:
            raise Exception("Initialize tool not called yet.")

        output = execute_bash(enc, arg, max_tokens, arg.wait_for_seconds)
    elif isinstance(arg, WriteIfEmpty):
        console.print("Calling write file tool")
        if not INITIALIZED:
            raise Exception("Initialize tool not called yet.")

        output = write_file(arg, True, max_tokens), 0
    elif isinstance(arg, FileEdit):
        console.print("Calling full file edit tool")
        if not INITIALIZED:
            raise Exception("Initialize tool not called yet.")

        output = do_diff_edit(arg, max_tokens), 0.0
    elif isinstance(arg, DoneFlag):
        console.print("Calling mark finish tool")
        output = mark_finish(arg), 0.0
    elif isinstance(arg, AIAssistant):
        console.print("Calling AI assistant tool")
        output = take_help_of_ai_assistant(arg, limit, loop_call)
    elif isinstance(arg, ReadImage):
        console.print("Calling read image tool")
        output = read_image_from_shell(arg.file_path), 0.0
    elif isinstance(arg, ReadFiles):
        console.print("Calling read file tool")
        output = read_files(arg.file_paths, max_tokens), 0.0
    elif isinstance(arg, ResetShell):
        console.print("Calling reset shell tool")
        output = reset_shell(), 0.0
    elif isinstance(arg, Initialize):
        console.print("Calling initial info tool")
        output = (
            initialize(
                arg.any_workspace_path,
                arg.initial_files_to_read,
                arg.task_id_to_resume,
                max_tokens,
                arg.mode,
            ),
            0.0,
        )
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
                        BashInteraction(send_text=f"export PS1={PROMPT}"),
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
    elif isinstance(arg, ContextSave):
        console.print("Calling task memory tool")
        assert not BASH_STATE.is_in_docker, "KT not supported in docker"
        relevant_files = []
        warnings = ""
        for fglob in arg.relevant_file_globs:
            fglob = expand_user(fglob, None)
            if not os.path.isabs(fglob) and arg.project_root_path:
                fglob = os.path.join(arg.project_root_path, fglob)
            globs = glob.glob(fglob, recursive=True)
            relevant_files.extend(globs[:1000])
            if not globs:
                warnings += f"Warning: No files found for the glob: {fglob}\n"
        relevant_files_data = read_files(relevant_files[:10_000], None)
        output_ = save_memory(arg, relevant_files_data, BASH_STATE.serialize())
        if not relevant_files and arg.relevant_file_globs:
            output_ = f'Error: No files found for the given globs. Context file successfully saved at "{output_}", but please fix the error.'
        elif warnings:
            output_ = warnings + "\nContext file successfully saved at " + output_
        output = output_, 0.0
    else:
        raise ValueError(f"Unknown tool: {arg}")
    if isinstance(output[0], str):
        console.print(str(output[0]))
    else:
        console.print(f"Received {type(output[0])} from tool")
    return [output[0]], output[1]


History = list[ChatCompletionMessageParam]

default_enc: tokenizers.Tokenizer = tokenizers.Tokenizer.from_pretrained(
    "Xenova/claude-tokenizer"
)
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
        | ReadFiles
        | Initialize
        | ContextSave
    )


def register_client(server_url: str, client_uuid: str = "") -> None:
    global default_enc, curr_cost
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


def read_files(file_paths: list[str], max_tokens: Optional[int]) -> str:
    message = ""
    for i, file in enumerate(file_paths):
        try:
            content, truncated, tokens = read_file(file, max_tokens)
        except Exception as e:
            message += f"\n{file}: {str(e)}\n"
            continue

        if max_tokens:
            max_tokens = max_tokens - tokens

        message += f"\n``` {file}\n{content}\n"

        if truncated or (max_tokens and max_tokens <= 0):
            not_reading = file_paths[i + 1 :]
            if not_reading:
                message += f'\nNot reading the rest of the files: {", ".join(not_reading)} due to token limit, please call again'
            break
        else:
            message += "```"

    return message


def read_file(file_path: str, max_tokens: Optional[int]) -> tuple[str, bool, int]:
    console.print(f"Reading file: {file_path}")

    # Expand the path before checking if it's absolute
    file_path = expand_user(file_path, BASH_STATE.is_in_docker)

    if not os.path.isabs(file_path):
        raise ValueError(
            f"Failure: file_path should be absolute path, current working directory is {BASH_STATE.cwd}"
        )

    BASH_STATE.add_to_whitelist_for_overwrite(file_path)

    if not BASH_STATE.is_in_docker:
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"Error: file {file_path} does not exist")

        with path.open("r") as f:
            content = f.read(10_000_000)

    else:
        return_code, content, stderr = command_run(
            f"docker exec {BASH_STATE.is_in_docker} cat {shlex.quote(file_path)}",
            timeout=TIMEOUT,
        )
        if return_code != 0:
            raise Exception(
                f"Error: cat {file_path} failed with code {return_code}\nstdout: {content}\nstderr: {stderr}"
            )

    truncated = False
    tokens_counts = 0
    if max_tokens is not None:
        tokens = default_enc.encode(content)
        tokens_counts = len(tokens)
        if len(tokens) > max_tokens:
            content = default_enc.decode(tokens.ids[:max_tokens])
            rest = save_out_of_context(
                default_enc.decode(tokens.ids[max_tokens:]), Path(file_path).suffix
            )
            content += f"\n(...truncated)\n---\nI've saved the continuation in a new file. Please read: `{rest}`"
            truncated = True
    return content, truncated, tokens_counts
