import datetime
import os
import platform
import re
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any, Literal, Optional

import pexpect
import pyte

from ...types_ import BashCommand, BashInteraction, Console, Modes
from ..encoder import EncoderDecoder
from ..modes import BashCommandMode, FileEditMode, WriteIfEmptyMode

PROMPT_CONST = "#" + "@wcgw@#"
BASH_CLF_OUTPUT = Literal["repl", "pending"]


@dataclass
class Config:
    timeout: float = 5
    timeout_while_output: float = 20
    output_wait_patience: float = 3

    def update(
        self, timeout: float, timeout_while_output: float, output_wait_patience: float
    ) -> None:
        self.timeout = timeout
        self.timeout_while_output = timeout_while_output
        self.output_wait_patience = output_wait_patience


CONFIG = Config()


def is_mac() -> bool:
    return platform.system() == "Darwin"


def get_tmpdir() -> str:
    current_tmpdir = os.environ.get("TMPDIR", "")
    if current_tmpdir or not is_mac():
        return current_tmpdir
    try:
        # Fix issue while running ocrmypdf -> tesseract -> leptonica, set TMPDIR
        # https://github.com/tesseract-ocr/tesseract/issues/4333
        result = subprocess.check_output(
            ["getconf", "DARWIN_USER_TEMP_DIR"],
            text=True,
        ).strip()
        return result
    except subprocess.CalledProcessError:
        return "//tmp"
    except Exception:
        return ""


def check_if_screen_command_available() -> bool:
    try:
        subprocess.run(["screen", "-v"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def start_shell(
    is_restricted_mode: bool, initial_dir: str, console: Console, over_screen: bool
) -> pexpect.spawn:  # type: ignore[type-arg]
    cmd = "/bin/bash"
    if is_restricted_mode:
        cmd += " -r"

    overrideenv = {
        **os.environ,
        "PS1": PROMPT_CONST,
        "TMPDIR": get_tmpdir(),
        "TERM": "vt100",
    }
    try:
        shell = pexpect.spawn(
            cmd,
            env=overrideenv,  # type: ignore[arg-type]
            echo=False,
            encoding="utf-8",
            timeout=CONFIG.timeout,
            cwd=initial_dir,
            codec_errors="backslashreplace",
            dimensions=(500, 160),
        )
        shell.sendline(
            f"export PROMPT_COMMAND= PS1={PROMPT_CONST}"
        )  # Unset prompt command to avoid interfering
        shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)
        console.log(shell.before or "")
    except Exception as e:
        console.print(traceback.format_exc())
        console.log(f"Error starting shell: {e}. Retrying without rc ...")

        shell = pexpect.spawn(
            "/bin/bash --noprofile --norc",
            env=overrideenv,  # type: ignore[arg-type]
            echo=False,
            encoding="utf-8",
            timeout=CONFIG.timeout,
            codec_errors="backslashreplace",
        )
        shell.sendline(f"export PS1={PROMPT_CONST}")
        shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)
        console.log(shell.before or "")

    if over_screen:
        if not check_if_screen_command_available():
            raise ValueError("Screen command not available")
        # shellid is just hour, minute, second number
        shellid = time.strftime("%H%M%S")
        shell.sendline(f"trap 'screen -X -S wcgw.{shellid} quit' EXIT")
        shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)
        console.log(shell.before or "")
        shell.sendline(f"screen -q -s /bin/bash -S wcgw.{shellid}")
        shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)
        console.log(shell.before or "")
        console.log(f"Entering screen session, name: wcgw.{shellid}")

    shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)
    console.log(shell.before or "")
    shell.sendline("stty -icanon -echo")
    shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)
    console.log(shell.before or "")
    shell.sendline("set +o pipefail")
    shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)
    console.log(shell.before or "")
    shell.sendline("export GIT_PAGER=cat PAGER=cat")
    shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)
    console.log(shell.before or "")
    return shell


def _is_int(mystr: str) -> bool:
    try:
        int(mystr)
        return True
    except ValueError:
        return False


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


class BashState:
    def __init__(
        self,
        console: Console,
        working_dir: str,
        bash_command_mode: Optional[BashCommandMode],
        file_edit_mode: Optional[FileEditMode],
        write_if_empty_mode: Optional[WriteIfEmptyMode],
        mode: Optional[Modes],
        whitelist_for_overwrite: Optional[set[str]] = None,
    ) -> None:
        self.console = console
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
        self._prompt = PROMPT_CONST
        self._bg_expect_thread: Optional[threading.Thread] = None
        self._bg_expect_thread_stop_event = threading.Event()
        self._init_shell()

    def expect(self, pattern: Any, timeout: Optional[float] = -1) -> int:
        self.close_bg_expect_thread()
        return self.shell.expect(pattern, timeout)

    def send(self, s: str | bytes) -> int:
        output = self.shell.send(s)
        self.run_bg_expect_thread()
        return output

    def sendline(self, s: str | bytes) -> int:
        output = self.shell.sendline(s)
        self.run_bg_expect_thread()
        return output

    def run_bg_expect_thread(self) -> None:
        """
        Run background expect thread for handling shell interactions.
        """

        def _bg_expect_thread_handler() -> None:
            while True:
                if self._bg_expect_thread_stop_event.is_set():
                    break
                output = self.shell.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=0.1)
                if output == 0:
                    break

        if self._bg_expect_thread:
            self.close_bg_expect_thread()

        self._bg_expect_thread = threading.Thread(
            target=_bg_expect_thread_handler,
        )
        self._bg_expect_thread.start()

    def close_bg_expect_thread(self) -> None:
        if self._bg_expect_thread:
            self._bg_expect_thread_stop_event.set()
            self._bg_expect_thread.join()
            self._bg_expect_thread = None
            self._bg_expect_thread_stop_event = threading.Event()

    def cleanup(self) -> None:
        self.close_bg_expect_thread()
        self.shell.close(True)

    def __enter__(self) -> "BashState":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.cleanup()

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

    def ensure_env_and_bg_jobs(self) -> Optional[int]:
        if self._prompt != PROMPT_CONST:
            return None
        quick_timeout = 0.2 if not self.over_screen else 1
        # First reset the prompt in case venv was sourced or other reasons.
        self.sendline(f"export PS1={self._prompt}")
        self.expect(self._prompt, timeout=quick_timeout)
        # Reset echo also if it was enabled
        self.sendline("stty -icanon -echo")
        self.expect(self._prompt, timeout=quick_timeout)
        self.sendline("set +o pipefail")
        self.expect(self._prompt, timeout=quick_timeout)
        self.sendline("export GIT_PAGER=cat PAGER=cat")
        self.expect(self._prompt, timeout=quick_timeout)
        self.sendline("jobs | wc -l")
        before = ""
        counts = 0
        while not _is_int(before):  # Consume all previous output
            try:
                self.expect(self._prompt, timeout=quick_timeout)
            except pexpect.TIMEOUT:
                self.console.print(f"Couldn't get exit code, before: {before}")
                raise

            before_val = self.shell.before
            if not isinstance(before_val, str):
                before_val = str(before_val)
            assert isinstance(before_val, str)
            before_lines = render_terminal_output(before_val)
            before = "\n".join(before_lines).strip()
            counts += 1
            if counts > 100:
                raise ValueError(
                    "Error in understanding shell output. This shouldn't happen, likely shell is in a bad state, please reset it"
                )

        try:
            return int(before)
        except ValueError:
            raise ValueError(f"Malformed output: {before}")

    def _init_shell(self) -> None:
        self._prompt = PROMPT_CONST
        self._state: Literal["repl"] | datetime.datetime = "repl"
        self._is_in_docker: Optional[str] = ""
        # Ensure self._cwd exists
        os.makedirs(self._cwd, exist_ok=True)
        try:
            self._shell = start_shell(
                self._bash_command_mode.bash_mode == "restricted_mode",
                self._cwd,
                self.console,
                over_screen=True,
            )
            self.over_screen = True
        except Exception as e:
            if not isinstance(e, ValueError):
                self.console.log(traceback.format_exc())
            self.console.log("Retrying without using screen")
            # Try without over_screen
            self._shell = start_shell(
                self._bash_command_mode.bash_mode == "restricted_mode",
                self._cwd,
                self.console,
                over_screen=False,
            )
            self.over_screen = False

        self._pending_output = ""

        # Get exit info to ensure shell is ready
        self.ensure_env_and_bg_jobs()

    @property
    def shell(self) -> pexpect.spawn:  # type: ignore
        return self._shell

    def set_pending(self, last_pending_output: str) -> None:
        if not isinstance(self._state, datetime.datetime):
            self._state = datetime.datetime.now()
        self._pending_output = last_pending_output
        self.run_bg_expect_thread()

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

    @property
    def prompt(self) -> str:
        return self._prompt

    def update_cwd(self) -> str:
        self.sendline("pwd")
        self.expect(self._prompt, timeout=0.2)
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
                            timedelta + datetime.timedelta(seconds=CONFIG.timeout)
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

    def update_repl_prompt(self, command: str) -> bool:
        if re.match(r"^wcgw_update_prompt\(\)$", command.strip()):
            self.shell.sendintr()
            index = self.expect([self._prompt, pexpect.TIMEOUT], timeout=0.2)
            if index == 0:
                return True
            before = self.shell.before or ""
            assert before, "Something went wrong updating repl prompt"
            self._prompt = before.split("\n")[-1].strip()
            # Escape all regex
            self._prompt = re.escape(self._prompt)
            self.console.print(f"Trying to update prompt to: {self._prompt.encode()!r}")
            index = 0
            counts = 0
            while index == 0:
                # Consume all REPL prompts till now
                index = self.expect([self._prompt, pexpect.TIMEOUT], timeout=0.2)
                counts += 1
                if counts > 100:
                    raise ValueError(
                        "Error in understanding shell output. This shouldn't happen, likely shell is in a bad state, please reset it"
                    )
            self.console.print(f"Prompt updated to: {self._prompt}")
            return True
        return False


WAITING_INPUT_MESSAGE = """A command is already running. NOTE: You can't run multiple shell sessions, likely a previous program hasn't exited. 
1. Get its output using `send_ascii: [10] or send_specials: ["Enter"]`
2. Use `send_ascii` or `send_specials` to give inputs to the running program, don't use `BashCommand` OR
3. kill the previous program by sending ctrl+c first using `send_ascii` or `send_specials`
4. Send the process in background using `send_specials: ["Ctrl-z"]` followed by BashCommand: `bg`
"""


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


def rstrip(lines: list[str]) -> str:
    return "\n".join([line.rstrip() for line in lines])


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


def get_status(bash_state: BashState) -> str:
    status = "\n\n---\n\n"
    if bash_state.state == "pending":
        status += "status = still running\n"
        status += "running for = " + bash_state.get_pending_for() + "\n"
        status += "cwd = " + bash_state.cwd + "\n"
    else:
        bg_jobs = bash_state.ensure_env_and_bg_jobs()
        bg_desc = ""
        if bg_jobs and bg_jobs > 0:
            bg_desc = f"; {bg_jobs} background jobs running"
        status += "status = process exited" + bg_desc + "\n"
        status += "cwd = " + bash_state.update_cwd() + "\n"

    return status.rstrip()


def is_status_check(arg: BashInteraction | BashCommand) -> bool:
    return isinstance(arg, BashInteraction) and (
        arg.send_specials == ["Enter"] or arg.send_ascii == [10]
    )


def execute_bash(
    bash_state: BashState,
    enc: EncoderDecoder[int],
    bash_arg: BashCommand | BashInteraction,
    max_tokens: Optional[int],
    timeout_s: Optional[float],
) -> tuple[str, float]:
    try:
        is_interrupt = False
        if isinstance(bash_arg, BashCommand):
            if bash_state.bash_command_mode.allowed_commands == "none":
                return "Error: BashCommand not allowed in current mode", 0.0
            updated_repl_mode = bash_state.update_repl_prompt(bash_arg.command)
            if updated_repl_mode:
                bash_state.set_repl()
                response = (
                    "Prompt updated, you can execute REPL lines using BashCommand now"
                )
                bash_state.console.print(response)
                return (
                    response,
                    0,
                )

            bash_state.console.print(f"$ {bash_arg.command}")
            if bash_state.state == "pending":
                raise ValueError(WAITING_INPUT_MESSAGE)
            command = bash_arg.command.strip()

            if "\n" in command:
                raise ValueError(
                    "Command should not contain newline character in middle. Run only one command at a time."
                )

            for i in range(0, len(command), 128):
                bash_state.send(command[i : i + 128])
            bash_state.send(bash_state.shell.linesep)

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
                bash_state.console.print(
                    f"Sending special sequence: {bash_arg.send_specials}"
                )
                for char in bash_arg.send_specials:
                    if char == "Key-up":
                        bash_state.send("\033[A")
                    elif char == "Key-down":
                        bash_state.send("\033[B")
                    elif char == "Key-left":
                        bash_state.send("\033[D")
                    elif char == "Key-right":
                        bash_state.send("\033[C")
                    elif char == "Enter":
                        bash_state.send("\n")
                    elif char == "Ctrl-c":
                        bash_state.shell.sendintr()
                        is_interrupt = True
                    elif char == "Ctrl-d":
                        bash_state.shell.sendintr()
                        is_interrupt = True
                    elif char == "Ctrl-z":
                        bash_state.send("\x1a")
                    else:
                        raise Exception(f"Unknown special character: {char}")
            elif bash_arg.send_ascii:
                bash_state.console.print(
                    f"Sending ASCII sequence: {bash_arg.send_ascii}"
                )
                for ascii_char in bash_arg.send_ascii:
                    bash_state.send(chr(ascii_char))
                    if ascii_char == 3:
                        is_interrupt = True
            else:
                if bash_arg.send_text is None:
                    return (
                        "Failure: at least one of send_text, send_specials or send_ascii should be provided",
                        0.0,
                    )

                updated_repl_mode = bash_state.update_repl_prompt(bash_arg.send_text)
                if updated_repl_mode:
                    bash_state.set_repl()
                    response = "Prompt updated, you can execute REPL lines using BashCommand now"
                    bash_state.console.print(response)
                    return (
                        response,
                        0,
                    )
                bash_state.console.print(f"Interact text: {bash_arg.send_text}")
                for i in range(0, len(bash_arg.send_text), 128):
                    bash_state.send(bash_arg.send_text[i : i + 128])
                bash_state.send(bash_state.shell.linesep)

    except KeyboardInterrupt:
        bash_state.shell.sendintr()
        bash_state.expect(bash_state.prompt)
        return "---\n\nFailure: user interrupted the execution", 0.0

    wait = min(timeout_s or CONFIG.timeout, CONFIG.timeout_while_output)
    index = bash_state.expect([bash_state.prompt, pexpect.TIMEOUT], timeout=wait)
    if index == 1:
        text = bash_state.shell.before or ""
        incremental_text = _incremental_text(text, bash_state.pending_output)

        second_wait_success = False
        if is_status_check(bash_arg):
            # There's some text in BashInteraction mode wait for TIMEOUT_WHILE_OUTPUT
            remaining = CONFIG.timeout_while_output - wait
            patience = CONFIG.output_wait_patience
            if not incremental_text:
                patience -= 1
            itext = incremental_text
            while remaining > 0 and patience > 0:
                index = bash_state.expect(
                    [bash_state.prompt, pexpect.TIMEOUT], timeout=wait
                )
                if index == 0:
                    second_wait_success = True
                    break
                else:
                    _itext = bash_state.shell.before or ""
                    _itext = _incremental_text(_itext, bash_state.pending_output)
                    if _itext != itext:
                        patience = 3
                    else:
                        patience -= 1
                    itext = _itext

                remaining = remaining - wait

            if not second_wait_success:
                text = bash_state.shell.before or ""
                incremental_text = _incremental_text(text, bash_state.pending_output)

        if not second_wait_success:
            bash_state.set_pending(text)

            tokens = enc.encoder(incremental_text)

            if max_tokens and len(tokens) >= max_tokens:
                incremental_text = "(...truncated)\n" + enc.decoder(
                    tokens[-(max_tokens - 1) :]
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

            exit_status = get_status(bash_state)
            incremental_text += exit_status

            return incremental_text, 0

    if not isinstance(bash_state.shell.before, str):
        bash_state.shell.before = str(bash_state.shell.before)

    output = _incremental_text(bash_state.shell.before, bash_state.pending_output)
    bash_state.set_repl()

    tokens = enc.encoder(output)
    if max_tokens and len(tokens) >= max_tokens:
        output = "(...truncated)\n" + enc.decoder(tokens[-(max_tokens - 1) :])

    try:
        exit_status = get_status(bash_state)
        output += exit_status
    except ValueError:
        bash_state.console.print(output)
        bash_state.console.print(traceback.format_exc())
        bash_state.console.print("Malformed output, restarting shell", style="red")
        # Malformed output, restart shell
        bash_state.reset_shell()
        output = "(exit shell has restarted)"
    return output, 0
