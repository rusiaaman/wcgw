import datetime
import json
import os
import platform
import random
import re
import shlex
import subprocess
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from hashlib import md5, sha256
from typing import (
    Any,
    Literal,
    Optional,
    ParamSpec,
    TypeVar,
)
from uuid import uuid4

import pexpect
import psutil
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
from .parser.bash_statement_parser import BashStatementParser

PROMPT_CONST = re.compile(r"◉ ([^\n]*)──➤")
PROMPT_COMMAND = "printf '◉ '\"$(pwd)\"'──➤'' \r\\e[2K'"
PROMPT_STATEMENT = ""
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
        return tempfile.gettempdir()
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
        return tempfile.gettempdir()


def check_if_screen_command_available() -> bool:
    try:
        subprocess.run(
            ["which", "screen"],
            capture_output=True,
            check=True,
            timeout=CONFIG.timeout,
        )

        # Check if screenrc exists, create it if it doesn't
        home_dir = os.path.expanduser("~")
        screenrc_path = os.path.join(home_dir, ".screenrc")

        if not os.path.exists(screenrc_path):
            screenrc_content = """defscrollback 10000
termcapinfo xterm* ti@:te@
"""
            with open(screenrc_path, "w") as f:
                f.write(screenrc_content)

        return True
    except (subprocess.CalledProcessError, FileNotFoundError, TimeoutError):
        return False


def get_wcgw_screen_sessions() -> list[str]:
    """
    Get a list of all WCGW screen session IDs.

    Returns:
        List of screen session IDs that match the wcgw pattern.
    """
    screen_sessions = []

    try:
        # Get list of all screen sessions
        result = subprocess.run(
            ["screen", "-ls"],
            capture_output=True,
            text=True,
            check=False,  # Don't raise exception on non-zero exit code
            timeout=0.5,
        )
        output = result.stdout or result.stderr or ""

        # Parse screen output to get session IDs
        for line in output.splitlines():
            line = line.strip()
            if not line or not line[0].isdigit():
                continue

            # Extract session info (e.g., "1234.wcgw.123456 (Detached)")
            session_parts = line.split()
            if not session_parts:
                continue

            session_id = session_parts[0].strip()

            # Check if it's a WCGW session
            if ".wcgw." in session_id:
                screen_sessions.append(session_id)
    except Exception:
        # If anything goes wrong, just return empty list
        pass

    return screen_sessions


def get_orphaned_wcgw_screens() -> list[str]:
    """
    Identify orphaned WCGW screen sessions where the parent process has PID 1
    or doesn't exist.

    Returns:
        List of screen session IDs that are orphaned and match the wcgw pattern.
    """
    orphaned_screens = []

    try:
        # Get list of all WCGW screen sessions
        screen_sessions = get_wcgw_screen_sessions()

        for session_id in screen_sessions:
            # Extract PID from session ID (first part before the dot)
            try:
                pid = int(session_id.split(".")[0])

                # Check if process exists and if its parent is PID 1
                try:
                    process = psutil.Process(pid)
                    parent_pid = process.ppid()

                    if parent_pid == 1:
                        # This is an orphaned process
                        orphaned_screens.append(session_id)
                except psutil.NoSuchProcess:
                    # Process doesn't exist anymore, consider it orphaned
                    orphaned_screens.append(session_id)
            except (ValueError, IndexError):
                # Couldn't parse PID, skip
                continue
    except Exception:
        # If anything goes wrong, just return empty list
        pass

    return orphaned_screens


def cleanup_orphaned_wcgw_screens(console: Console) -> None:
    """
    Clean up all orphaned WCGW screen sessions.

    Args:
        console: Console for logging.
    """
    orphaned_sessions = get_orphaned_wcgw_screens()

    if not orphaned_sessions:
        return

    console.log(
        f"Found {len(orphaned_sessions)} orphaned WCGW screen sessions to clean up"
    )

    for session in orphaned_sessions:
        try:
            subprocess.run(
                ["screen", "-S", session, "-X", "quit"],
                check=False,
                timeout=CONFIG.timeout,
            )
        except Exception as e:
            console.log(f"Failed to kill orphaned screen session: {session}\n{e}")


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
            timeout=CONFIG.timeout,
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


def get_rc_file_path(shell_path: str) -> Optional[str]:
    """
    Get the rc file path for the given shell.

    Args:
        shell_path: Path to the shell executable

    Returns:
        Path to the rc file or None if not supported
    """
    shell_name = os.path.basename(shell_path)
    home_dir = os.path.expanduser("~")

    if shell_name == "zsh":
        return os.path.join(home_dir, ".zshrc")
    elif shell_name == "bash":
        return os.path.join(home_dir, ".bashrc")
    else:
        return None


def ensure_wcgw_block_in_rc_file(shell_path: str, console: Console) -> None:
    """
    Ensure the WCGW environment block exists in the appropriate rc file.

    Args:
        shell_path: Path to the shell executable
        console: Console for logging
    """
    rc_file_path = get_rc_file_path(shell_path)
    if not rc_file_path:
        return

    shell_name = os.path.basename(shell_path)

    # Define the WCGW block with marker comments
    marker_start = "# --WCGW_ENVIRONMENT_START--"
    marker_end = "# --WCGW_ENVIRONMENT_END--"

    if shell_name == "zsh":
        wcgw_block = f"""{marker_start}
if [ -n "$IN_WCGW_ENVIRONMENT" ]; then
 PROMPT_COMMAND='printf "◉ $(pwd)──➤ \\r\\e[2K"'
 prmptcmdwcgw() {{ eval "$PROMPT_COMMAND" }}
 add-zsh-hook -d precmd prmptcmdwcgw
 precmd_functions+=prmptcmdwcgw
fi
{marker_end}
"""
    elif shell_name == "bash":
        wcgw_block = f"""{marker_start}
if [ -n "$IN_WCGW_ENVIRONMENT" ]; then
 PROMPT_COMMAND='printf "◉ $(pwd)──➤ \\r\\e[2K"'
fi
{marker_end}
"""
    else:
        return

    # Check if rc file exists
    if not os.path.exists(rc_file_path):
        # Create the rc file with the WCGW block
        try:
            with open(rc_file_path, "w") as f:
                f.write(wcgw_block)
            console.log(f"Created {rc_file_path} with WCGW environment block")
        except Exception as e:
            console.log(f"Failed to create {rc_file_path}: {e}")
        return

    # Check if the block already exists
    try:
        with open(rc_file_path) as f:
            content = f.read()

        if marker_start in content:
            # Block already exists
            return

        # Append the block to the file
        with open(rc_file_path, "a") as f:
            f.write("\n" + wcgw_block)
        console.log(f"Added WCGW environment block to {rc_file_path}")
    except Exception as e:
        console.log(f"Failed to update {rc_file_path}: {e}")


def start_shell(
    is_restricted_mode: bool,
    initial_dir: str,
    console: Console,
    over_screen: bool,
    shell_path: str,
) -> tuple["pexpect.spawn[str]", str]:
    cmd = shell_path
    if is_restricted_mode and cmd.split("/")[-1] == "bash":
        cmd += " -r"

    overrideenv = {
        **os.environ,
        "PROMPT_COMMAND": PROMPT_COMMAND,
        "TMPDIR": get_tmpdir(),
        "TERM": "xterm-256color",
        "IN_WCGW_ENVIRONMENT": "1",
        "GIT_PAGER": "cat",
        "PAGER": "cat",
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
        shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)
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
        shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)

    initialdir_hash = md5(
        os.path.normpath(os.path.abspath(initial_dir)).encode()
    ).hexdigest()[:5]
    shellid = shlex.quote(
        "wcgw."
        + time.strftime("%d-%Hh%Mm%Ss")
        + f".{initialdir_hash[:3]}."
        + os.path.basename(initial_dir)
    )
    if over_screen:
        if not check_if_screen_command_available():
            raise ValueError("Screen command not available")
        # shellid is just hour, minute, second number
        while True:
            output = shell.expect([PROMPT_CONST, pexpect.TIMEOUT], timeout=0.1)
            if output == 1:
                break
        shell.sendline(f"screen -q -S {shellid} {shell_path}")
        shell.expect(PROMPT_CONST, timeout=CONFIG.timeout)

    return shell, shellid


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


def get_bash_state_dir_xdg() -> str:
    """Get the XDG directory for storing bash state."""
    xdg_data_dir = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    bash_state_dir = os.path.join(xdg_data_dir, "wcgw", "bash_state")
    os.makedirs(bash_state_dir, exist_ok=True)
    return bash_state_dir


def generate_thread_id() -> str:
    """Generate a random 4-digit thread_id."""
    return f"i{random.randint(1000, 9999)}"


def save_bash_state_by_id(thread_id: str, bash_state_dict: dict[str, Any]) -> None:
    """Save bash state to XDG directory with the given thread_id."""
    if not thread_id:
        return

    bash_state_dir = get_bash_state_dir_xdg()
    state_file = os.path.join(bash_state_dir, f"{thread_id}_bash_state.json")

    with open(state_file, "w") as f:
        json.dump(bash_state_dict, f, indent=2)


def load_bash_state_by_id(thread_id: str) -> Optional[dict[str, Any]]:
    """Load bash state from XDG directory with the given thread_id."""
    if not thread_id:
        return None

    bash_state_dir = get_bash_state_dir_xdg()
    state_file = os.path.join(bash_state_dir, f"{thread_id}_bash_state.json")

    if not os.path.exists(state_file):
        return None

    with open(state_file) as f:
        return json.load(f)  # type: ignore


class BashState:
    _use_screen: bool
    _current_thread_id: str

    def __init__(
        self,
        console: Console,
        working_dir: str,
        bash_command_mode: Optional[BashCommandMode],
        file_edit_mode: Optional[FileEditMode],
        write_if_empty_mode: Optional[WriteIfEmptyMode],
        mode: Optional[Modes],
        use_screen: bool,
        whitelist_for_overwrite: Optional[dict[str, "FileWhitelistData"]] = None,
        thread_id: Optional[str] = None,
        shell_path: Optional[str] = None,
    ) -> None:
        self.last_command: str = ""
        self.console = console
        self._cwd = working_dir or os.getcwd()
        # Store the workspace root separately from the current working directory
        self._workspace_root = working_dir or os.getcwd()
        self._bash_command_mode: BashCommandMode = bash_command_mode or BashCommandMode(
            "normal_mode", "all"
        )
        self._file_edit_mode: FileEditMode = file_edit_mode or FileEditMode("all")
        self._write_if_empty_mode: WriteIfEmptyMode = (
            write_if_empty_mode or WriteIfEmptyMode("all")
        )
        self._mode: Modes = mode or "wcgw"
        self._whitelist_for_overwrite: dict[str, FileWhitelistData] = (
            whitelist_for_overwrite or {}
        )
        # Always ensure we have a thread_id
        self._current_thread_id = (
            thread_id if thread_id is not None else generate_thread_id()
        )
        self._bg_expect_thread: Optional[threading.Thread] = None
        self._bg_expect_thread_stop_event = threading.Event()
        self._use_screen = use_screen
        # Ensure shell_path is always a str, never None
        self._shell_path: str = (
            shell_path if shell_path else os.environ.get("SHELL", "/bin/bash")
        )
        if get_rc_file_path(self._shell_path) is None:
            console.log(
                f"Warning: Unsupported shell: {self._shell_path}, defaulting to /bin/bash"
            )
            self._shell_path = "/bin/bash"

        self.background_shells = dict[str, BashState]()
        self._init_shell()

    def start_new_bg_shell(self, working_dir: str) -> "BashState":
        cid = uuid4().hex[:10]
        state = BashState(
            self.console,
            working_dir=working_dir,
            bash_command_mode=self.bash_command_mode,
            file_edit_mode=self.file_edit_mode,
            write_if_empty_mode=self.write_if_empty_mode,
            mode=self.mode,
            use_screen=self.over_screen,
            whitelist_for_overwrite=None,
            thread_id=cid,
            shell_path=self._shell_path,
        )
        self.background_shells[cid] = state
        return state

    def expect(
        self, pattern: Any, timeout: Optional[float] = -1, flush_rem_prompt: bool = True
    ) -> int:
        self.close_bg_expect_thread()
        try:
            output = self._shell.expect(pattern, timeout)
            if isinstance(self._shell.match, re.Match) and self._shell.match.groups():
                cwd = self._shell.match.group(1)
                if cwd.strip():
                    self._cwd = cwd
                    # We can safely flush current prompt
                    if flush_rem_prompt:
                        temp_before = self._shell.before
                        self.flush_prompt()
                        self._shell.before = temp_before
        except pexpect.TIMEOUT:
            # Edge case: gets raised when the child fd is not ready in some timeout
            # pexpect/utils.py:143
            return 1
        return output

    def flush_prompt(self) -> None:
        # Flush remaining prompt
        for _ in range(200):
            try:
                output = self.expect([" ", pexpect.TIMEOUT], 0.1)
                if output == 1:
                    return
            except pexpect.TIMEOUT:
                return

    def send(self, s: str | bytes, set_as_command: Optional[str]) -> int:
        if set_as_command is not None:
            self.last_command = set_as_command
        # if s == "\n":
        #     return self._shell.sendcontrol("m")
        output = self._shell.send(s)
        return output

    def sendline(self, s: str | bytes, set_as_command: Optional[str]) -> int:
        if set_as_command is not None:
            self.last_command = set_as_command
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
        if before and before.startswith(self.last_command):
            return before[len(self.last_command) :]
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
        for k, v in self.background_shells.items():
            v.run_bg_expect_thread()

    def close_bg_expect_thread(self) -> None:
        if self._bg_expect_thread:
            self._bg_expect_thread_stop_event.set()
            self._bg_expect_thread.join()
            self._bg_expect_thread = None
            self._bg_expect_thread_stop_event = threading.Event()
        for k, v in self.background_shells.items():
            v.close_bg_expect_thread()

    def cleanup(self) -> None:
        self.close_bg_expect_thread()
        self._shell.close(True)

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

    def _init_shell(self) -> None:
        self._state: Literal["repl"] | datetime.datetime = "repl"
        self.last_command = ""
        # Ensure self._cwd exists
        os.makedirs(self._cwd, exist_ok=True)

        # Ensure WCGW block exists in rc file
        ensure_wcgw_block_in_rc_file(self._shell_path, self.console)

        # Clean up orphaned WCGW screen sessions
        if check_if_screen_command_available():
            cleanup_orphaned_wcgw_screens(self.console)

        try:
            self._shell, self._shell_id = start_shell(
                self._bash_command_mode.bash_mode == "restricted_mode",
                self._cwd,
                self.console,
                over_screen=self._use_screen,
                shell_path=self._shell_path,
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
                shell_path=self._shell_path,
            )
            self.over_screen = False

        self._pending_output = ""

        self.run_bg_expect_thread()

    def set_pending(self, last_pending_output: str) -> None:
        if not isinstance(self._state, datetime.datetime):
            self._state = datetime.datetime.now()
        self._pending_output = last_pending_output

    def set_repl(self) -> None:
        self._state = "repl"
        self._pending_output = ""
        self.last_command = ""

    def clear_to_run(self) -> None:
        """Check if prompt is clear to enter new command otherwise send ctrl c"""
        # First clear
        starttime = time.time()
        self.close_bg_expect_thread()
        try:
            while True:
                try:
                    output = self.expect(
                        [PROMPT_CONST, pexpect.TIMEOUT], 0.1, flush_rem_prompt=False
                    )
                    if output == 1:
                        break
                except pexpect.TIMEOUT:
                    break
                if time.time() - starttime > CONFIG.timeout:
                    self.console.log(
                        f"Error: could not clear output in {CONFIG.timeout} seconds. Resetting"
                    )
                    self.reset_shell()
                    return
            output = self.expect([" ", pexpect.TIMEOUT], 0.1)
            if output != 1:
                # Then we got something new send ctrl-c
                self.send("\x03", None)

                output = self.expect([PROMPT_CONST, pexpect.TIMEOUT], CONFIG.timeout)
                if output == 1:
                    self.console.log("Error: could not clear output. Resetting")
                    self.reset_shell()
        finally:
            self.run_bg_expect_thread()

    @property
    def state(self) -> BASH_CLF_OUTPUT:
        if self._state == "repl":
            return "repl"
        return "pending"

    @property
    def cwd(self) -> str:
        return self._cwd

    @property
    def workspace_root(self) -> str:
        """Return the workspace root directory."""
        return self._workspace_root

    def set_workspace_root(self, workspace_root: str) -> None:
        """Set the workspace root directory."""
        self._workspace_root = workspace_root

    @property
    def prompt(self) -> re.Pattern[str]:
        return PROMPT_CONST

    def reset_shell(self) -> None:
        self.cleanup()
        self._init_shell()

    @property
    def current_thread_id(self) -> str:
        """Get the current thread_id."""
        return self._current_thread_id

    def load_state_from_thread_id(self, thread_id: str) -> bool:
        """
        Load bash state from a thread_id.

        Args:
            thread_id: The thread_id to load state from

        Returns:
            bool: True if state was successfully loaded, False otherwise
        """
        # Try to load state from disk
        loaded_state = load_bash_state_by_id(thread_id)
        if not loaded_state:
            return False

        # Parse and load the state
        parsed_state = BashState.parse_state(loaded_state)
        self.load_state(
            parsed_state[0],
            parsed_state[1],
            parsed_state[2],
            parsed_state[3],
            parsed_state[4],
            parsed_state[5],
            parsed_state[5],
            thread_id,
        )
        return True

    def serialize(self) -> dict[str, Any]:
        """Serialize BashState to a dictionary for saving"""
        return {
            "bash_command_mode": self._bash_command_mode.serialize(),
            "file_edit_mode": self._file_edit_mode.serialize(),
            "write_if_empty_mode": self._write_if_empty_mode.serialize(),
            "whitelist_for_overwrite": {
                k: v.serialize() for k, v in self._whitelist_for_overwrite.items()
            },
            "mode": self._mode,
            "workspace_root": self._workspace_root,
            "chat_id": self._current_thread_id,
        }

    def save_state_to_disk(self) -> None:
        """Save the current bash state to disk using the thread_id."""
        state_dict = self.serialize()
        save_bash_state_by_id(self._current_thread_id, state_dict)

    @staticmethod
    def parse_state(
        state: dict[str, Any],
    ) -> tuple[
        BashCommandMode,
        FileEditMode,
        WriteIfEmptyMode,
        Modes,
        dict[str, "FileWhitelistData"],
        str,
        str,
    ]:
        whitelist_state = state["whitelist_for_overwrite"]
        # Convert serialized whitelist data back to FileWhitelistData objects
        whitelist_dict = {}
        if isinstance(whitelist_state, dict):
            for file_path, data in whitelist_state.items():
                if isinstance(data, dict) and "file_hash" in data:
                    # New format
                    whitelist_dict[file_path] = FileWhitelistData.deserialize(data)
                else:
                    # Legacy format (just a hash string)
                    # Try to get line count from file if it exists, otherwise use a large default
                    whitelist_dict[file_path] = FileWhitelistData(
                        file_hash=data if isinstance(data, str) else "",
                        line_ranges_read=[(1, 1000000)],  # Assume entire file was read
                        total_lines=1000000,
                    )
        else:
            # Handle really old format if needed
            whitelist_dict = {
                k: FileWhitelistData(
                    file_hash="", line_ranges_read=[(1, 1000000)], total_lines=1000000
                )
                for k in whitelist_state
            }

        # Get the thread_id from state, or generate a new one if not present
        thread_id = state.get("chat_id")
        if thread_id is None:
            thread_id = generate_thread_id()

        return (
            BashCommandMode.deserialize(state["bash_command_mode"]),
            FileEditMode.deserialize(state["file_edit_mode"]),
            WriteIfEmptyMode.deserialize(state["write_if_empty_mode"]),
            state["mode"],
            whitelist_dict,
            state.get("workspace_root", ""),
            thread_id,
        )

    def load_state(
        self,
        bash_command_mode: BashCommandMode,
        file_edit_mode: FileEditMode,
        write_if_empty_mode: WriteIfEmptyMode,
        mode: Modes,
        whitelist_for_overwrite: dict[str, "FileWhitelistData"],
        cwd: str,
        workspace_root: str,
        thread_id: str,
    ) -> None:
        """Create a new BashState instance from a serialized state dictionary"""
        self._bash_command_mode = bash_command_mode
        self._cwd = cwd or self._cwd
        self._workspace_root = workspace_root or cwd or self._workspace_root
        self._file_edit_mode = file_edit_mode
        self._write_if_empty_mode = write_if_empty_mode
        self._whitelist_for_overwrite = dict(whitelist_for_overwrite)
        self._mode = mode
        self._current_thread_id = thread_id
        self.reset_shell()

        # Save state to disk after loading
        self.save_state_to_disk()

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
    def whitelist_for_overwrite(self) -> dict[str, "FileWhitelistData"]:
        return self._whitelist_for_overwrite

    def add_to_whitelist_for_overwrite(
        self, file_paths_with_ranges: dict[str, list[tuple[int, int]]]
    ) -> None:
        """
        Add files to the whitelist for overwrite.

        Args:
            file_paths_with_ranges: Dictionary mapping file paths to sequences of
                               (start_line, end_line) tuples representing
                               the ranges that have been read.
        """
        for file_path, ranges in file_paths_with_ranges.items():
            # Read the file to get its hash and count lines
            with open(file_path, "rb") as f:
                file_content = f.read()
                file_hash = sha256(file_content).hexdigest()
                total_lines = file_content.count(b"\n") + 1

            # Update or create whitelist entry
            if file_path in self._whitelist_for_overwrite:
                # Update existing entry
                whitelist_data = self._whitelist_for_overwrite[file_path]
                whitelist_data.file_hash = file_hash
                whitelist_data.total_lines = total_lines
                for range_start, range_end in ranges:
                    whitelist_data.add_range(range_start, range_end)
            else:
                # Create new entry
                self._whitelist_for_overwrite[file_path] = FileWhitelistData(
                    file_hash=file_hash,
                    line_ranges_read=list(ranges),
                    total_lines=total_lines,
                )

    @property
    def pending_output(self) -> str:
        return self._pending_output


@dataclass
class FileWhitelistData:
    """Data about a file that has been read and can be modified."""

    file_hash: str
    # List of line ranges that have been read (inclusive start, inclusive end)
    # E.g., [(1, 10), (20, 30)] means lines 1-10 and 20-30 have been read
    line_ranges_read: list[tuple[int, int]]
    # Total number of lines in the file
    total_lines: int

    def get_percentage_read(self) -> float:
        """Calculate percentage of file read based on line ranges."""
        if self.total_lines == 0:
            return 100.0

        # Count unique lines read
        lines_read: set[int] = set()
        for start, end in self.line_ranges_read:
            lines_read.update(range(start, end + 1))

        return (len(lines_read) / self.total_lines) * 100.0

    def is_read_enough(self) -> bool:
        """Check if enough of the file has been read (>=99%)"""
        return self.get_percentage_read() >= 99

    def get_unread_ranges(self) -> list[tuple[int, int]]:
        """Return a list of line ranges (start, end) that haven't been read yet.

        Returns line ranges as tuples of (start_line, end_line) in 1-indexed format.
        If the whole file has been read, returns an empty list.
        """
        if self.total_lines == 0:
            return []

        # First collect all lines that have been read
        lines_read: set[int] = set()
        for start, end in self.line_ranges_read:
            lines_read.update(range(start, end + 1))

        # Generate unread ranges from the gaps
        unread_ranges: list[tuple[int, int]] = []
        start_range = None

        for i in range(1, self.total_lines + 1):
            if i not in lines_read:
                if start_range is None:
                    start_range = i
            elif start_range is not None:
                # End of an unread range
                unread_ranges.append((start_range, i - 1))
                start_range = None

        # Don't forget the last range if it extends to the end of the file
        if start_range is not None:
            unread_ranges.append((start_range, self.total_lines))

        return unread_ranges

    def add_range(self, start: int, end: int) -> None:
        """Add a new range of lines that have been read."""
        # Merge with existing ranges if possible
        self.line_ranges_read.append((start, end))
        # Could add range merging logic here for optimization

    def serialize(self) -> dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "file_hash": self.file_hash,
            "line_ranges_read": self.line_ranges_read,
            "total_lines": self.total_lines,
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "FileWhitelistData":
        """Create from a serialized dictionary."""
        return cls(
            file_hash=data.get("file_hash", ""),
            line_ranges_read=data.get("line_ranges_read", []),
            total_lines=data.get("total_lines", 0),
        )


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


def get_status(bash_state: BashState, is_bg: bool) -> str:
    status = "\n\n---\n\n"
    if is_bg:
        status += f"bg_command_id = {bash_state.current_thread_id}\n"
    if bash_state.state == "pending":
        status += "status = still running\n"
        status += "running for = " + bash_state.get_pending_for() + "\n"
        status += "cwd = " + bash_state.cwd + "\n"
    else:
        bg_desc = ""
        status += "status = process exited" + bg_desc + "\n"
        status += "cwd = " + bash_state.cwd + "\n"

    if not is_bg:
        status += "This is the main shell. " + get_bg_running_commandsinfo(bash_state)

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
    max_tokens: Optional[int],  # This will be noncoding_max_tokens
    timeout_s: Optional[float],
) -> tuple[str, float]:
    try:
        # Check if the thread_id matches current
        if bash_arg.thread_id != bash_state.current_thread_id:
            # Try to load state from the thread_id
            if not bash_state.load_state_from_thread_id(bash_arg.thread_id):
                return (
                    f"Error: No saved bash state found for thread_id {bash_arg.thread_id}. Please initialize first with this ID.",
                    0.0,
                )

        output, cost = _execute_bash(bash_state, enc, bash_arg, max_tokens, timeout_s)

        # Remove echo if it's a command
        if isinstance(bash_arg.action_json, Command):
            command = bash_arg.action_json.command.strip()
            if output.startswith(command):
                output = output[len(command) :]

    finally:
        bash_state.run_bg_expect_thread()
        if bash_state.over_screen:
            thread = threading.Thread(
                target=cleanup_orphaned_wcgw_screens,
                args=(bash_state.console,),
                daemon=True,
            )
            thread.start()
    return output, cost


def assert_single_statement(command: str) -> None:
    # Check for multiple statements using the bash statement parser
    if "\n" in command:
        try:
            parser = BashStatementParser()
            statements = parser.parse_string(command)
        except Exception:
            # Fall back to simple newline check if something goes wrong
            raise ValueError(
                "Command should not contain newline character in middle. Run only one command at a time."
            )
        if len(statements) > 1:
            raise ValueError(
                "Error: Command contains multiple statements. Please run only one bash statement at a time."
            )


def get_bg_running_commandsinfo(bash_state: BashState) -> str:
    msg = ""
    running = []
    for id_, state in bash_state.background_shells.items():
        running.append(f"Command: {state.last_command}, bg_command_id: {id_}")
    if running:
        msg = (
            "Following background commands are attached:\n" + "\n".join(running) + "\n"
        )
    else:
        msg = "No command running in background.\n"
    return msg


def _execute_bash(
    bash_state: BashState,
    enc: EncoderDecoder[int],
    bash_arg: BashCommand,
    max_tokens: Optional[int],  # This will be noncoding_max_tokens
    timeout_s: Optional[float],
) -> tuple[str, float]:
    try:
        is_interrupt = False
        command_data = bash_arg.action_json
        is_bg = False
        og_bash_state = bash_state

        if not isinstance(command_data, Command) and command_data.bg_command_id:
            if command_data.bg_command_id not in bash_state.background_shells:
                error = f"No shell found running with command id {command_data.bg_command_id}.\n"
                if bash_state.background_shells:
                    error += get_bg_running_commandsinfo(bash_state)
                if bash_state.state == "pending":
                    error += f"On the main thread a command is already running ({bash_state.last_command})"
                else:
                    error += "On the main thread no command is running."
                raise Exception(error)
            bash_state = bash_state.background_shells[command_data.bg_command_id]
            is_bg = True

        if isinstance(command_data, Command):
            if bash_state.bash_command_mode.allowed_commands == "none":
                return "Error: BashCommand not allowed in current mode", 0.0

            bash_state.console.print(f"$ {command_data.command}")

            if bash_state.state == "pending":
                raise ValueError(WAITING_INPUT_MESSAGE)

            command = command_data.command.strip()

            assert_single_statement(command)

            if command_data.is_background:
                bash_state = bash_state.start_new_bg_shell(bash_state.cwd)
                is_bg = True

            bash_state.clear_to_run()
            for i in range(0, len(command), 64):
                bash_state.send(command[i : i + 64], set_as_command=None)
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
                    bash_state.send("\x0d", set_as_command=None)
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

            exit_status = get_status(bash_state, is_bg)
            incremental_text += exit_status
            if is_bg and bash_state.state == "repl":
                try:
                    bash_state.cleanup()
                    og_bash_state.background_shells.pop(bash_state.current_thread_id)
                except Exception as e:
                    bash_state.console.log(f"error while cleaning up {e}")

            return incremental_text, 0

    before = str(bash_state.before)

    output = _incremental_text(before, bash_state.pending_output)
    bash_state.set_repl()

    tokens = enc.encoder(output)
    if max_tokens and len(tokens) >= max_tokens:
        output = "(...truncated)\n" + enc.decoder(tokens[-(max_tokens - 1) :])

    try:
        exit_status = get_status(bash_state, is_bg)
        output += exit_status
        if is_bg and bash_state.state == "repl":
            try:
                bash_state.cleanup()
                og_bash_state.background_shells.pop(bash_state.current_thread_id)
            except Exception as e:
                bash_state.console.log(f"error while cleaning up {e}")
    except ValueError:
        bash_state.console.print(output)
        bash_state.console.print(traceback.format_exc())
        bash_state.console.print("Malformed output, restarting shell", style="red")
        # Malformed output, restart shell
        bash_state.reset_shell()
        output = "(exit shell has restarted)"
    return output, 0
