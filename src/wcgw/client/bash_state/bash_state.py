import datetime
import os
import platform
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass
from typing import (
    Any,
    Literal,
    Optional,
    ParamSpec,
    TypeVar,
)

import pexpect
import pyte

from ...types_ import (
    BashCommand,
    Command,
    Console,
    Modes,
    SendAscii,
    SendSpecials,
    SendText,
    StatusCheck,
)
from ..encoder import EncoderDecoder
from ..modes import BashCommandMode, FileEditMode, WriteIfEmptyMode

PROMPT_CONST = "wcgw→" + " "
PROMPT_STATEMENT = "export GIT_PAGER=cat PAGER=cat PROMPT_COMMAND= PS1='wcgw→'' '"
BASH_CLF_OUTPUT = Literal["repl", "pending"]
os.environ["TOKENIZERS_PARALLELISM"] = "false"


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
            timeout=CONFIG.timeout,
        ).strip()
        return result
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "//tmp"
    except Exception:
        return ""


def check_if_screen_command_available() -> bool:
    try:
        subprocess.run(
            ["which", "screen"], capture_output=True, check=True, timeout=0.2
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def cleanup_all_screens_with_name(name: str, console: Console) -> None:
    """
    There could be in worst case multiple screens with same name, clear them if any.
    Clearing just using "screen -X -S {name} quit" doesn't work because screen complains
    that there are several suitable screens.
    """
    try:
        # Try to get the list of screens.
        result = subprocess.run(
            ["screen", "-ls"],
            capture_output=True,
            text=True,
            check=True,
            timeout=0.2,
        )
        output = result.stdout
    except subprocess.CalledProcessError as e:
        # When no screens exist, screen may return a non-zero exit code.
        output = (e.stdout or "") + (e.stderr or "")
    except FileNotFoundError:
        return
    except Exception as e:
        console.log(f"{e}: exception while clearing running screens.")
        return

    sessions_to_kill = []

    # Parse each line of the output. The lines containing sessions typically start with a digit.
    for line in output.splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue

        # Each session is usually shown as "1234.my_screen (Detached)".
        # We extract the first part, then split on the period to get the session name.
        session_info = line.split()[0].strip()  # e.g., "1234.my_screen"
        if session_info.endswith(f".{name}"):
            sessions_to_kill.append(session_info)

    # Now, for every session we found, tell screen to quit it.
    for session in sessions_to_kill:
        try:
            subprocess.run(
                ["screen", "-S", session, "-X", "quit"],
                check=True,
                timeout=CONFIG.timeout,
            )
        except Exception as e:
            console.log(f"Failed to kill screen session: {session}\n{e}")


def start_shell(
    is_restricted_mode: bool, initial_dir: str, console: Console, over_screen: bool
) -> tuple["pexpect.spawn[str]", str]:
    cmd = "/bin/bash"
    if is_restricted_mode:
        cmd += " -r"

    overrideenv = {
        **os.environ,
        "PS1": PROMPT_CONST,
        "TMPDIR": get_tmpdir(),
        "TERM": "xterm-256color",
    }
    try:
        shell = pexpect.spawn(
            cmd,
            env=overrideenv,  # type: ignore[arg-type]
            echo=True,
            encoding="utf-8",
            timeout=CONFIG.timeout,
            cwd=initial_dir,
            codec_errors="backslashreplace",
            dimensions=(500, 160),
        )
        shell.sendline(PROMPT_STATEMENT)  # Unset prompt command to avoid interfering
        shell.expect(PROMPT_CONST, timeout=0.2)
    except Exception as e:
        console.print(traceback.format_exc())
        console.log(f"Error starting shell: {e}. Retrying without rc ...")

        shell = pexpect.spawn(
            "/bin/bash --noprofile --norc",
            env=overrideenv,  # type: ignore[arg-type]
            echo=True,
            encoding="utf-8",
            timeout=CONFIG.timeout,
            codec_errors="backslashreplace",
        )
        shell.sendline(PROMPT_STATEMENT)
        shell.expect(PROMPT_CONST, timeout=0.2)

    shellid = "wcgw." + time.strftime("%H%M%S")
    if over_screen:
        if not check_if_screen_command_available():
            raise ValueError("Screen command not available")
        # shellid is just hour, minute, second number
        shell.sendline(f"trap 'screen -X -S {shellid} quit' EXIT")
        shell.expect(PROMPT_CONST, timeout=0.2)

        shell.sendline(f"screen -q -S {shellid} /bin/bash --noprofile --norc")
        shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)

    return shell, shellid


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


P = ParamSpec("P")
R = TypeVar("R")


class BashState:
    _use_screen: bool

    def __init__(
        self,
        console: Console,
        working_dir: str,
        bash_command_mode: Optional[BashCommandMode],
        file_edit_mode: Optional[FileEditMode],
        write_if_empty_mode: Optional[WriteIfEmptyMode],
        mode: Optional[Modes],
        use_screen: bool,
        whitelist_for_overwrite: Optional[set[str]] = None,
    ) -> None:
        self._last_command: str = ""
        self.console = console
        self._cwd = working_dir or os.getcwd()
        self._bash_command_mode: BashCommandMode = bash_command_mode or BashCommandMode(
            "normal_mode", "all"
        )
        self._file_edit_mode: FileEditMode = file_edit_mode or FileEditMode("all")
        self._write_if_empty_mode: WriteIfEmptyMode = (
            write_if_empty_mode or WriteIfEmptyMode("all")
        )
        self._mode = mode or "wcgw"
        self._whitelist_for_overwrite: set[str] = whitelist_for_overwrite or set()
        self._bg_expect_thread: Optional[threading.Thread] = None
        self._bg_expect_thread_stop_event = threading.Event()
        self._use_screen = use_screen
        self._init_shell()

    def expect(self, pattern: Any, timeout: Optional[float] = -1) -> int:
        self.close_bg_expect_thread()
        output = self._shell.expect(pattern, timeout)
        return output

    def send(self, s: str | bytes, set_as_command: Optional[str]) -> int:
        self.close_bg_expect_thread()
        if set_as_command is not None:
            self._last_command = set_as_command
        output = self._shell.send(s)
        return output

    def sendline(self, s: str | bytes, set_as_command: Optional[str]) -> int:
        self.close_bg_expect_thread()
        if set_as_command is not None:
            self._last_command = set_as_command
        output = self._shell.sendline(s)
        return output

    @property
    def linesep(self) -> Any:
        return self._shell.linesep

    def sendintr(self) -> None:
        self.close_bg_expect_thread()
        self._shell.sendintr()

    @property
    def before(self) -> Optional[str]:
        before = self._shell.before
        if before and before.startswith(self._last_command):
            return before[len(self._last_command) :]
        return before

    def run_bg_expect_thread(self) -> None:
        """
        Run background expect thread for handling shell interactions.
        """

        def _bg_expect_thread_handler() -> None:
            while True:
                if self._bg_expect_thread_stop_event.is_set():
                    break
                output = self._shell.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=0.1)
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
        self._shell.close(True)
        cleanup_all_screens_with_name(self._shell_id, self.console)

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
        quick_timeout = 0.2 if not self.over_screen else 1
        # First reset the prompt in case venv was sourced or other reasons.
        self.sendline(PROMPT_STATEMENT, set_as_command=PROMPT_STATEMENT)
        self.expect(PROMPT_CONST, timeout=quick_timeout)
        # Reset echo also if it was enabled
        command = "jobs | wc -l"
        self.sendline(command, set_as_command=command)
        before = ""
        counts = 0
        while not _is_int(before):  # Consume all previous output
            try:
                self.expect(PROMPT_CONST, timeout=quick_timeout)
            except pexpect.TIMEOUT:
                self.console.print(f"Couldn't get exit code, before: {before}")
                raise

            before_val = self.before
            if not isinstance(before_val, str):
                before_val = str(before_val)
            assert isinstance(before_val, str)
            before_lines = render_terminal_output(before_val)
            before = "\n".join(before_lines).replace(command, "").strip()
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
        self._state: Literal["repl"] | datetime.datetime = "repl"
        self._last_command = ""
        # Ensure self._cwd exists
        os.makedirs(self._cwd, exist_ok=True)
        try:
            self._shell, self._shell_id = start_shell(
                self._bash_command_mode.bash_mode == "restricted_mode",
                self._cwd,
                self.console,
                over_screen=self._use_screen,
            )
            self.over_screen = self._use_screen
        except Exception as e:
            if not isinstance(e, ValueError):
                self.console.log(traceback.format_exc())
            self.console.log("Retrying without using screen")
            # Try without over_screen
            self._shell, self._shell_id = start_shell(
                self._bash_command_mode.bash_mode == "restricted_mode",
                self._cwd,
                self.console,
                over_screen=False,
            )
            self.over_screen = False

        self._pending_output = ""
        try:
            self.ensure_env_and_bg_jobs()
        except ValueError as e:
            self.console.log("Error while running _ensure_env_and_bg_jobs" + str(e))

        self.run_bg_expect_thread()

    def set_pending(self, last_pending_output: str) -> None:
        if not isinstance(self._state, datetime.datetime):
            self._state = datetime.datetime.now()
        self._pending_output = last_pending_output

    def set_repl(self) -> None:
        self._state = "repl"
        self._pending_output = ""
        self._last_command = ""

    @property
    def state(self) -> BASH_CLF_OUTPUT:
        if self._state == "repl":
            return "repl"
        return "pending"

    @property
    def cwd(self) -> str:
        return self._cwd

    @property
    def prompt(self) -> str:
        return PROMPT_CONST

    def update_cwd(self) -> str:
        self.sendline("pwd", set_as_command="pwd")
        self.expect(PROMPT_CONST, timeout=0.2)
        before_val = self.before
        if not isinstance(before_val, str):
            before_val = str(before_val)
        before_lines = render_terminal_output(before_val)
        current_dir = "\n".join(before_lines).strip()
        if current_dir.startswith("pwd"):
            current_dir = current_dir[3:].strip()
        self._cwd = current_dir
        return current_dir

    def reset_shell(self) -> None:
        self.cleanup()
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
            state["mode"],
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


WAITING_INPUT_MESSAGE = """A command is already running. NOTE: You can't run multiple shell sessions, likely a previous program hasn't exited. 
1. Get its output using status check.
2. Use `send_ascii` or `send_specials` to give inputs to the running program OR
3. kill the previous program by sending ctrl+c first using `send_ascii` or `send_specials`
4. Interrupt and run the process in background by re-running it using screen
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

    if not last_pending_output:
        # This is the first call. We need to offset the position where this program
        # is being rendered for the new screen versions
        # Caveat: no difference in output between a program with leading whitespace and one without.
        return rstrip(render_terminal_output(text)).lstrip()
    last_rendered_lines = render_terminal_output(last_pending_output)
    last_pending_output_rendered = "\n".join(last_rendered_lines)
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


def is_status_check(arg: BashCommand) -> bool:
    return (
        isinstance(arg.action_json, StatusCheck)
        or (
            isinstance(arg.action_json, SendSpecials)
            and arg.action_json.send_specials == ["Enter"]
        )
        or (
            isinstance(arg.action_json, SendAscii)
            and arg.action_json.send_ascii == [10]
        )
    )


def execute_bash(
    bash_state: BashState,
    enc: EncoderDecoder[int],
    bash_arg: BashCommand,
    max_tokens: Optional[int],
    timeout_s: Optional[float],
) -> tuple[str, float]:
    try:
        output, cost = _execute_bash(bash_state, enc, bash_arg, max_tokens, timeout_s)

        # Remove echo if it's a command
        if isinstance(bash_arg.action_json, Command):
            command = bash_arg.action_json.command.strip()
            if output.startswith(command):
                output = output[len(command) :]

    finally:
        bash_state.run_bg_expect_thread()
    return output, cost


def _execute_bash(
    bash_state: BashState,
    enc: EncoderDecoder[int],
    bash_arg: BashCommand,
    max_tokens: Optional[int],
    timeout_s: Optional[float],
) -> tuple[str, float]:
    try:
        is_interrupt = False
        command_data = bash_arg.action_json

        if isinstance(command_data, Command):
            if bash_state.bash_command_mode.allowed_commands == "none":
                return "Error: BashCommand not allowed in current mode", 0.0

            bash_state.console.print(f"$ {command_data.command}")

            if bash_state.state == "pending":
                raise ValueError(WAITING_INPUT_MESSAGE)

            command = command_data.command.strip()
            if "\n" in command:
                raise ValueError(
                    "Command should not contain newline character in middle. Run only one command at a time."
                )

            for i in range(0, len(command), 128):
                bash_state.send(command[i : i + 128], set_as_command=None)
            bash_state.send(bash_state.linesep, set_as_command=command)

        elif isinstance(command_data, StatusCheck):
            bash_state.console.print("Checking status")
            if bash_state.state != "pending":
                return "No running command to check status of", 0.0

        elif isinstance(command_data, SendText):
            if not command_data.send_text:
                return "Failure: send_text cannot be empty", 0.0

            bash_state.console.print(f"Interact text: {command_data.send_text}")
            for i in range(0, len(command_data.send_text), 128):
                bash_state.send(
                    command_data.send_text[i : i + 128], set_as_command=None
                )
            bash_state.send(bash_state.linesep, set_as_command=None)

        elif isinstance(command_data, SendSpecials):
            if not command_data.send_specials:
                return "Failure: send_specials cannot be empty", 0.0

            bash_state.console.print(
                f"Sending special sequence: {command_data.send_specials}"
            )
            for char in command_data.send_specials:
                if char == "Key-up":
                    bash_state.send("\033[A", set_as_command=None)
                elif char == "Key-down":
                    bash_state.send("\033[B", set_as_command=None)
                elif char == "Key-left":
                    bash_state.send("\033[D", set_as_command=None)
                elif char == "Key-right":
                    bash_state.send("\033[C", set_as_command=None)
                elif char == "Enter":
                    bash_state.send("\n", set_as_command=None)
                elif char == "Ctrl-c":
                    bash_state.sendintr()
                    is_interrupt = True
                elif char == "Ctrl-d":
                    bash_state.sendintr()
                    is_interrupt = True
                elif char == "Ctrl-z":
                    bash_state.send("\x1a", set_as_command=None)
                else:
                    raise Exception(f"Unknown special character: {char}")

        elif isinstance(command_data, SendAscii):
            if not command_data.send_ascii:
                return "Failure: send_ascii cannot be empty", 0.0

            bash_state.console.print(
                f"Sending ASCII sequence: {command_data.send_ascii}"
            )
            for ascii_char in command_data.send_ascii:
                bash_state.send(chr(ascii_char), set_as_command=None)
                if ascii_char == 3:
                    is_interrupt = True
        else:
            raise ValueError(f"Unknown command type: {type(command_data)}")

    except KeyboardInterrupt:
        bash_state.sendintr()
        bash_state.expect(bash_state.prompt)
        return "---\n\nFailure: user interrupted the execution", 0.0

    wait = min(timeout_s or CONFIG.timeout, CONFIG.timeout_while_output)
    index = bash_state.expect([bash_state.prompt, pexpect.TIMEOUT], timeout=wait)
    if index == 1:
        text = bash_state.before or ""
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
                    _itext = bash_state.before or ""
                    _itext = _incremental_text(_itext, bash_state.pending_output)
                    if _itext != itext:
                        patience = 3
                    else:
                        patience -= 1
                    itext = _itext

                remaining = remaining - wait

            if not second_wait_success:
                text = bash_state.before or ""
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
You may want to try Ctrl-c again or program specific exit interactive commands.
    """
                )

            exit_status = get_status(bash_state)
            incremental_text += exit_status

            return incremental_text, 0

    before = str(bash_state.before)

    output = _incremental_text(before, bash_state.pending_output)
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
