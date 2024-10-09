import asyncio
import json
import sys
import threading
import traceback
from typing import Callable, Literal, Optional, ParamSpec, Sequence, TypeVar, TypedDict
import uuid
from pydantic import BaseModel, TypeAdapter

import os
import tiktoken
import petname  # type: ignore[import]
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

from .common import CostData, Models, discard_input

from .openai_utils import get_input_cost, get_output_cost

console = rich.console.Console(style="magenta", highlight=False)

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
    return "\n".join(screen.display[: len(dsp) - i])


class Confirmation(BaseModel):
    prompt: str


def ask_confirmation(prompt: Confirmation) -> str:
    response = input(prompt.prompt + " [y/n] ")
    return "Yes" if response.lower() == "y" else "No"


class Writefile(BaseModel):
    file_path: str
    file_content: str


def start_shell():
    SHELL = pexpect.spawn(
        "/bin/bash",
        env={**os.environ, **{"PS1": "#@@"}},
        echo=False,
        encoding="utf-8",
        timeout=TIMEOUT,
    )  # type: ignore[arg-type]
    SHELL.expect("#@@")
    SHELL.sendline("stty -icanon -echo")
    SHELL.expect("#@@")
    return SHELL


SHELL = start_shell()


def _get_exit_code() -> int:
    SHELL.sendline("echo $?")
    SHELL.expect("#@@")
    assert isinstance(SHELL.before, str)
    return int((SHELL.before))


Specials = Literal["Key-up", "Key-down", "Key-left", "Key-right", "Enter", "Ctrl-c"]


class ExecuteBash(BaseModel):
    execute_command: Optional[str] = None
    send_ascii: Optional[Sequence[int | Specials]] = None


class GetShellOutputLastCommand(BaseModel):
    type: Literal["get_output_of_last_command"] = "get_output_of_last_command"


BASH_CLF_OUTPUT = Literal["running", "waiting_for_input", "wont_exit"]
BASH_STATE: BASH_CLF_OUTPUT = "running"


def get_output_of_last_command(enc: tiktoken.Encoding) -> str:
    global SHELL, BASH_STATE
    output = render_terminal_output(SHELL.before)

    tokens = enc.encode(output)
    if len(tokens) >= 2048:
        output = "...(truncated)\n" + enc.decode(tokens[-2047:])

    return output


WETTING_INPUT_MESSAGE = """A command is already running waiting for input. NOTE: You can't run multiple shell sessions, likely a previous program hasn't exited. 
1. Get its output using `GetShellOutputLastCommand` OR
2. Use  `send_ascii` to give inputs to the running program, don't use `execute_command` OR
3. kill the previous program by sending ctrl+c first using `send_ascii`"""


def execute_bash(
    enc: tiktoken.Encoding,
    bash_arg: ExecuteBash,
    is_waiting_user_input: Callable[[str], tuple[BASH_CLF_OUTPUT, float]],
) -> tuple[str, float]:
    global SHELL, BASH_STATE
    try:
        if bash_arg.execute_command:
            if BASH_STATE == "waiting_for_input":
                raise ValueError(WETTING_INPUT_MESSAGE)
            elif BASH_STATE == "wont_exit":
                raise ValueError(
                    """A command is already running that hasn't exited. NOTE: You can't run multiple shell sessions, likely a previous program is in infinite loop.
                    Kill the previous program by sending ctrl+c first using `send_ascii`"""
                )
            command = bash_arg.execute_command.strip()

            if "\n" in command:
                raise ValueError(
                    "Command should not contain newline character in middle. Run only one command at a time."
                )

            console.print(f"$ {command}")
            SHELL.sendline(command)
        elif bash_arg.send_ascii:
            console.print(f"Sending ASCII sequence: {bash_arg.send_ascii}")
            for char in bash_arg.send_ascii:
                if isinstance(char, int):
                    SHELL.send(chr(char))
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
        else:
            raise Exception("Nothing to send")
        BASH_STATE = "running"

    except KeyboardInterrupt:
        SHELL.close(True)
        SHELL = start_shell()
        raise

    wait = timeout = 5
    index = SHELL.expect(["#@@", pexpect.TIMEOUT], timeout=wait)
    running = ""
    while index == 1:
        if wait > TIMEOUT:
            raise TimeoutError("Timeout while waiting for shell prompt")

        text = SHELL.before
        print(text[len(running) :])
        running = text

        text = render_terminal_output(text)
        BASH_STATE, cost = is_waiting_user_input(text)
        if BASH_STATE == "waiting_for_input" or BASH_STATE == "wont_exit":
            tokens = enc.encode(text)

            if len(tokens) >= 2048:
                text = "...(truncated)\n" + enc.decode(tokens[-2047:])

            last_line = (
                "(waiting for input)"
                if BASH_STATE == "waiting_for_input"
                else "(won't exit)"
            )
            return text + f"\n{last_line}", cost
        index = SHELL.expect(["#@@", pexpect.TIMEOUT], timeout=wait)
        wait += timeout

    assert isinstance(SHELL.before, str)
    output = render_terminal_output(SHELL.before)

    tokens = enc.encode(output)
    if len(tokens) >= 2048:
        output = "...(truncated)\n" + enc.decode(tokens[-2047:])

    try:
        exit_code = _get_exit_code()
        output += f"\n(exit {exit_code})"

    except ValueError:
        console.print("Malformed output, restarting shell", style="red")
        # Malformed output, restart shell
        SHELL.close(True)
        SHELL = start_shell()
        output = "(exit shell has restarted)"
    return output, 0


Param = ParamSpec("Param")

T = TypeVar("T")


def ensure_no_previous_output(func: Callable[Param, T]) -> Callable[Param, T]:
    def wrapper(*args: Param.args, **kwargs: Param.kwargs) -> T:
        global BASH_STATE
        if BASH_STATE == "waiting_for_input":
            raise ValueError(WETTING_INPUT_MESSAGE)
        elif BASH_STATE == "wont_exit":
            raise ValueError(
                "A command is already running that hasn't exited. NOTE: You can't run multiple shell sessions, likely the previous program is in infinite loop. Please kill the previous program by sending ctrl+c first."
            )
        return func(*args, **kwargs)

    return wrapper


@ensure_no_previous_output
def write_file(writefile: Writefile) -> str:
    if not os.path.isabs(writefile.file_path):
        SHELL.sendline("pwd")
        SHELL.expect("#@@")
        assert isinstance(SHELL.before, str)
        current_dir = SHELL.before.strip()
        writefile.file_path = os.path.join(current_dir, writefile.file_path)
    os.makedirs(os.path.dirname(writefile.file_path), exist_ok=True)
    try:
        with open(writefile.file_path, "w") as f:
            f.write(writefile.file_content)
    except OSError as e:
        console.print(f"Error: {e}", style="red")
        return f"Error: {e}"
    console.print(f"File written to {writefile.file_path}")
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


class AddTasks(BaseModel):
    task_statement: str


def add_task(addtask: AddTasks) -> str:
    petname_id = petname.Generate(2, "-")
    return petname_id


class RemoveTask(BaseModel):
    task_id: str


def remove_task(removetask: RemoveTask) -> str:
    return "removed"


def which_tool(args: str) -> BaseModel:
    adapter = TypeAdapter[
        Confirmation | ExecuteBash | Writefile | AIAssistant | DoneFlag
    ](Confirmation | ExecuteBash | Writefile | AIAssistant | DoneFlag)
    return adapter.validate_python(json.loads(args))


def get_tool_output(
    args: dict | Confirmation | ExecuteBash | Writefile | AIAssistant | DoneFlag,
    enc: tiktoken.Encoding,
    limit: float,
    loop_call: Callable[[str, float], tuple[str, float]],
    is_waiting_user_input: Callable[[str], tuple[BASH_CLF_OUTPUT, float]],
) -> tuple[str | DoneFlag, float]:
    if isinstance(args, dict):
        adapter = TypeAdapter[
            Confirmation | ExecuteBash | Writefile | AIAssistant | DoneFlag
        ](Confirmation | ExecuteBash | Writefile | AIAssistant | DoneFlag)
        arg = adapter.validate_python(args)
    else:
        arg = args
    output: tuple[str | DoneFlag, float]
    if isinstance(arg, Confirmation):
        console.print("Calling ask confirmation tool")
        output = ask_confirmation(arg), 0.0
    elif isinstance(arg, ExecuteBash):
        console.print("Calling execute bash tool")
        output = execute_bash(enc, arg, is_waiting_user_input)
    elif isinstance(arg, Writefile):
        console.print("Calling write file tool")
        output = write_file(arg), 0
    elif isinstance(arg, DoneFlag):
        console.print("Calling mark finish tool")
        output = mark_finish(arg), 0.0
    elif isinstance(arg, AIAssistant):
        console.print("Calling AI assistant tool")
        output = take_help_of_ai_assistant(arg, limit, loop_call)
    elif isinstance(arg, AddTasks):
        console.print("Calling add task tool")
        output = add_task(arg), 0
    elif isinstance(arg, get_output_of_last_command):
        console.print("Calling get output of last program tool")
        output = get_output_of_last_command(enc), 0
    else:
        raise ValueError(f"Unknown tool: {arg}")

    console.print(str(output[0]))
    return output


History = list[ChatCompletionMessageParam]


def get_is_waiting_user_input(model: Models, cost_data: CostData):
    enc = tiktoken.encoding_for_model(model if not model.startswith("o1") else "gpt-4o")
    system_prompt = """You need to classify if a bash program is waiting for user input based on its stdout, or if it won't exit. You'll be given the output of any program.
    Return `waiting_for_input` if the program is waiting for INTERACTIVE input only, Return false if it's waiting for external resources or just waiting to finish.
    Return `wont_exit` if the program won't exit, for example if it's a server.
    Return `normal` otherwise.
    """
    history: History = [{"role": "system", "content": system_prompt}]
    client = OpenAI()

    class ExpectedOutput(BaseModel):
        output_classified: BASH_CLF_OUTPUT

    def is_waiting_user_input(output: str) -> tuple[BASH_CLF_OUTPUT, float]:
        # Send only last 30 lines
        output = "\n".join(output.split("\n")[-30:])
        # Send only max last 200 tokens
        output = enc.decode(enc.encode(output)[-200:])

        history.append({"role": "user", "content": output})
        response = client.beta.chat.completions.parse(
            model=model, messages=history, response_format=ExpectedOutput
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("No parsed output")
        cost = (
            get_input_cost(cost_data, enc, history)[0]
            + get_output_cost(cost_data, enc, response.choices[0].message)[0]
        )
        return parsed.output_classified, cost

    return is_waiting_user_input


default_enc = tiktoken.encoding_for_model("gpt-4o")
default_model: Models = "gpt-4o-2024-08-06"
default_cost = CostData(cost_per_1m_input_tokens=0.15, cost_per_1m_output_tokens=0.6)
curr_cost = 0.0


class Mdata(BaseModel):
    data: ExecuteBash | Writefile


execution_lock = threading.Lock()


def execute_user_input() -> None:
    while True:
        discard_input()
        user_input = input()
        if user_input:
            with execution_lock:
                try:
                    console.log(
                        execute_bash(
                            default_enc,
                            ExecuteBash(
                                send_ascii=[ord(x) for x in user_input] + [ord("\n")]
                            ),
                            lambda x: ("wont_exit", 0),
                        )[0]
                    )
                except Exception as e:
                    traceback.print_exc()
                    console.log(f"Error: {e}")


async def register_client(server_url: str) -> None:
    global default_enc, default_model, curr_cost
    # Generate a unique UUID for this client
    client_uuid = str(uuid.uuid4())
    print(f"Connecting with UUID: {client_uuid}")

    # Create the WebSocket connection
    async with websockets.connect(f"{server_url}/{client_uuid}") as websocket:
        try:
            while True:
                # Wait to receive data from the server
                message = await websocket.recv()
                print(message, type(message))
                mdata = Mdata.model_validate_json(message)
                with execution_lock:
                    is_waiting_user_input = get_is_waiting_user_input(
                        default_model, default_cost
                    )
                    try:
                        output, cost = get_tool_output(
                            mdata.data,
                            default_enc,
                            0.0,
                            lambda x, y: ("", 0),
                            is_waiting_user_input,
                        )
                        curr_cost += cost
                        print(f"{curr_cost=}")
                    except Exception as e:
                        output = f"GOT EXCEPTION while calling tool. Error: {e}"
                        traceback.print_exc()
                    assert not isinstance(output, DoneFlag)
                    await websocket.send(output)

        except websockets.ConnectionClosed:
            print(f"Connection closed for UUID: {client_uuid}")


def run() -> None:
    if len(sys.argv) > 1:
        server_url = sys.argv[1]
    else:
        server_url = "ws://localhost:8000/register"
    asyncio.run(register_client(server_url))
