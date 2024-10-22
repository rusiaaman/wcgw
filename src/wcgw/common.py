import select
import sys
import termios
import tty
from typing import Literal
from pydantic import BaseModel


class CostData(BaseModel):
    cost_per_1m_input_tokens: float
    cost_per_1m_output_tokens: float


from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ParsedChatCompletionMessage,
)

History = list[ChatCompletionMessageParam]
Models = Literal["gpt-4o-2024-08-06", "gpt-4o-mini"]


def discard_input() -> None:
    try:
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
                    sys.stdin.read(1)  # Read one character at a time to flush the input buffer
                else:
                    break
        finally:
            # Restore old terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except (termios.error, ValueError) as e:
        # Handle the error gracefully
        print(f"Warning: Unable to discard input. Error: {e}")
