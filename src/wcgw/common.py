import os
import select
import subprocess
import sys
import tempfile
import termios
import tty
from typing import Literal
from pydantic import BaseModel
import rich


class CostData(BaseModel):
    cost_per_1m_input_tokens: float
    cost_per_1m_output_tokens: float


Models = Literal["gpt-4o-2024-08-06", "gpt-4o-mini"]


def discard_input() -> None:
    # Get the file descriptor for stdin
    fd = sys.stdin.fileno()

    # Save current terminal settings
    old_settings = termios.tcgetattr(fd)

    try:
        # Switch terminal to non-canonical mode where input is read immediately
        tty.setcbreak(fd)

        # Discard all input
        while True:
            # Check if there is input to be read
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.read(
                    1
                )  # Read one character at a time to flush the input buffer
            else:
                break
    finally:
        # Restore old terminal settings
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


class Config(BaseModel):
    model: Models
    secondary_model: Models
    cost_limit: float
    cost_file: dict[Models, CostData]
    cost_unit: str = "$"


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
