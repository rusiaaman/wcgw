import base64
import json
import mimetypes
import os
import subprocess
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Literal, Optional, cast

import rich
from anthropic import Anthropic, MessageStopEvent
from anthropic.types import (
    ImageBlockParam,
    MessageParam,
    ModelParam,
    RawMessageStartEvent,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
)
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
from typer import Typer

from wcgw.client.bash_state.bash_state import BashState
from wcgw.client.common import CostData, discard_input
from wcgw.client.memory import load_memory
from wcgw.client.tool_prompts import TOOL_PROMPTS
from wcgw.client.tools import (
    Context,
    ImageData,
    default_enc,
    get_tool_output,
    initialize,
    parse_tool_by_name,
)


class Config(BaseModel):
    model: ModelParam
    cost_limit: float
    cost_file: dict[ModelParam, CostData]
    cost_unit: str = "$"


History = list[MessageParam]


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


def save_history(history: History, session_id: str) -> None:
    myid = str(history[1]["content"]).replace("/", "_").replace(" ", "_").lower()[:60]
    myid += "_" + session_id
    myid = myid + ".json"

    mypath = Path(".wcgw") / myid
    mypath.parent.mkdir(parents=True, exist_ok=True)
    with open(mypath, "w") as f:
        json.dump(history, f, indent=3)


def parse_user_message_special(msg: str) -> MessageParam:
    # Search for lines starting with `%` and treat them as special commands
    parts: list[ImageBlockParam | TextBlockParam] = []
    for line in msg.split("\n"):
        if line.startswith("%"):
            args = line[1:].strip().split(" ")
            command = args[0]
            assert command == "image"
            image_path = " ".join(args[1:])
            with open(image_path, "rb") as f:
                image_bytes = f.read()
                image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                image_type = mimetypes.guess_type(image_path)[0]
            parts.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": cast(
                            'Literal["image/jpeg", "image/png", "image/gif", "image/webp"]',
                            image_type or "image/png",
                        ),
                        "data": image_b64,
                    },
                }
            )
        else:
            if len(parts) > 0 and parts[-1]["type"] == "text":
                parts[-1]["text"] += "\n" + line
            else:
                parts.append({"type": "text", "text": line})
    return {"role": "user", "content": parts}


app = Typer(pretty_exceptions_show_locals=False)


@app.command()
def loop(
    first_message: Optional[str] = None,
    limit: Optional[float] = None,
    resume: Optional[str] = None,
) -> tuple[str, float]:
    load_dotenv()

    session_id = str(uuid.uuid4())[:6]

    history: History = []
    waiting_for_assistant = False
    memory = None
    if resume:
        try:
            _, memory, _ = load_memory(
                resume,
                8000,
                lambda x: default_enc.encoder(x),
                lambda x: default_enc.decoder(x),
            )
        except OSError:
            if resume == "latest":
                resume_path = sorted(Path(".wcgw").iterdir(), key=os.path.getmtime)[-1]
            else:
                resume_path = Path(resume)
            if not resume_path.exists():
                raise FileNotFoundError(f"File {resume} not found")
            with resume_path.open() as f:
                history = json.load(f)
            if len(history) <= 2:
                raise ValueError("Invalid history file")
            first_message = ""
            waiting_for_assistant = history[-1]["role"] != "assistant"

    config = Config(
        model="claude-3-5-sonnet-20241022",
        cost_limit=0.1,
        cost_unit="$",
        cost_file={
            # Claude 3.5 Haiku
            "claude-3-5-haiku-latest": CostData(
                cost_per_1m_input_tokens=0.80, cost_per_1m_output_tokens=4
            ),
            "claude-3-5-haiku-20241022": CostData(
                cost_per_1m_input_tokens=0.80, cost_per_1m_output_tokens=4
            ),
            # Claude 3.5 Sonnet
            "claude-3-5-sonnet-latest": CostData(
                cost_per_1m_input_tokens=3.0, cost_per_1m_output_tokens=15.0
            ),
            "claude-3-5-sonnet-20241022": CostData(
                cost_per_1m_input_tokens=3.0, cost_per_1m_output_tokens=15.0
            ),
            "claude-3-5-sonnet-20240620": CostData(
                cost_per_1m_input_tokens=3.0, cost_per_1m_output_tokens=15.0
            ),
            # Claude 3 Opus
            "claude-3-opus-latest": CostData(
                cost_per_1m_input_tokens=15.0, cost_per_1m_output_tokens=75.0
            ),
            "claude-3-opus-20240229": CostData(
                cost_per_1m_input_tokens=15.0, cost_per_1m_output_tokens=75.0
            ),
            # Legacy Models
            "claude-3-haiku-20240307": CostData(
                cost_per_1m_input_tokens=0.25, cost_per_1m_output_tokens=1.25
            ),
            "claude-2.1": CostData(
                cost_per_1m_input_tokens=8.0, cost_per_1m_output_tokens=24.0
            ),
            "claude-2.0": CostData(
                cost_per_1m_input_tokens=8.0, cost_per_1m_output_tokens=24.0
            ),
        },
    )

    if limit is not None:
        config.cost_limit = limit
    limit = config.cost_limit

    tools = [
        ToolParam(
            name=tool.name,
            description=tool.description,
            input_schema=tool.inputSchema,
        )
        for tool in TOOL_PROMPTS
        if tool.name != "Initialize"
    ]

    system_console = rich.console.Console(style="blue", highlight=False, markup=False)
    error_console = rich.console.Console(style="red", highlight=False, markup=False)
    user_console = rich.console.Console(
        style="bright_black", highlight=False, markup=False
    )
    assistant_console = rich.console.Console(
        style="white bold", highlight=False, markup=False
    )

    with BashState(
        system_console, os.getcwd(), None, None, None, None, True, None
    ) as bash_state:
        context = Context(bash_state, system_console)
        system, context = initialize(
            "first_call",
            context,
            os.getcwd(),
            [],
            resume if (memory and resume) else "",
            max_tokens=8000,
            mode="wcgw",
        )

        if history:
            if (
                (last_msg := history[-1])["role"] == "user"
                and isinstance((content := last_msg["content"]), dict)
                and content["type"] == "tool_result"
            ):
                waiting_for_assistant = True

        client = Anthropic()

        cost: float = 0
        input_toks = 0
        output_toks = 0

        while True:
            if cost > limit:
                system_console.print(
                    f"\nCost limit exceeded. Current cost: {config.cost_unit}{cost:.4f}, "
                    f"input tokens: {input_toks}"
                    f"output tokens: {output_toks}"
                )
                break
            else:
                system_console.print(
                    f"\nTotal cost: {config.cost_unit}{cost:.4f}, input tokens: {input_toks}, output tokens: {output_toks}"
                )

            if not waiting_for_assistant:
                if first_message:
                    msg = first_message
                    first_message = ""
                else:
                    msg = text_from_editor(user_console)

                history.append(parse_user_message_special(msg))
            else:
                waiting_for_assistant = False

            stream = client.messages.stream(
                model=config.model,
                messages=history,
                tools=tools,
                max_tokens=8096,
                system=system,
            )

            system_console.print(
                "\n---------------------------------------\n# Assistant response",
                style="bold",
            )
            _histories: History = []
            full_response: str = ""

            tool_calls = []
            tool_results: list[ToolResultBlockParam] = []
            try:
                with stream as stream_:
                    for chunk in stream_:
                        type_ = chunk.type
                        if isinstance(chunk, RawMessageStartEvent):
                            message_start = chunk.message
                            # Update cost based on token usage from the API response
                            input_tokens = message_start.usage.input_tokens
                            input_toks += input_tokens
                            cost += (
                                input_tokens
                                * config.cost_file[
                                    config.model
                                ].cost_per_1m_input_tokens
                            ) / 1_000_000
                        elif isinstance(chunk, MessageStopEvent):
                            message_stop = chunk.message
                            # Update cost based on output tokens
                            output_tokens = message_stop.usage.output_tokens
                            output_toks += output_tokens
                            cost += (
                                output_tokens
                                * config.cost_file[
                                    config.model
                                ].cost_per_1m_output_tokens
                            ) / 1_000_000
                            continue
                        elif type_ == "content_block_start" and hasattr(
                            chunk, "content_block"
                        ):
                            content_block = chunk.content_block
                            if (
                                hasattr(content_block, "type")
                                and content_block.type == "text"
                                and hasattr(content_block, "text")
                            ):
                                chunk_str = content_block.text
                                assistant_console.print(chunk_str, end="")
                                full_response += chunk_str
                            elif content_block.type == "tool_use":
                                if (
                                    hasattr(content_block, "input")
                                    and hasattr(content_block, "name")
                                    and hasattr(content_block, "id")
                                ):
                                    assert content_block.input == {}
                                    tool_calls.append(
                                        {
                                            "name": str(content_block.name),
                                            "input": str(""),
                                            "done": False,
                                            "id": str(content_block.id),
                                        }
                                    )
                            else:
                                error_console.log(
                                    f"Ignoring unknown content block type {content_block.type}"
                                )
                        elif type_ == "content_block_delta" and hasattr(chunk, "delta"):
                            delta = chunk.delta
                            if hasattr(delta, "type"):
                                delta_type = str(delta.type)
                                if delta_type == "text_delta" and hasattr(
                                    delta, "text"
                                ):
                                    chunk_str = delta.text
                                    assistant_console.print(chunk_str, end="")
                                    full_response += chunk_str
                                elif delta_type == "input_json_delta" and hasattr(
                                    delta, "partial_json"
                                ):
                                    partial_json = delta.partial_json
                                    if isinstance(tool_calls[-1]["input"], str):
                                        tool_calls[-1]["input"] += partial_json
                                else:
                                    error_console.log(
                                        f"Ignoring unknown content block delta type {delta_type}"
                                    )
                            else:
                                raise ValueError("Content block delta has no type")
                        elif type_ == "content_block_stop":
                            if tool_calls and not tool_calls[-1]["done"]:
                                tc = tool_calls[-1]
                                tool_name = str(tc["name"])
                                tool_input = str(tc["input"])
                                tool_id = str(tc["id"])

                                _histories.append(
                                    {
                                        "role": "assistant",
                                        "content": [
                                            ToolUseBlockParam(
                                                id=tool_id,
                                                name=tool_name,
                                                input=json.loads(tool_input),
                                                type="tool_use",
                                            )
                                        ],
                                    }
                                )
                                try:
                                    tool_parsed = parse_tool_by_name(
                                        tool_name, json.loads(tool_input)
                                    )
                                except ValidationError:
                                    error_msg = f"Error parsing tool {tool_name}\n{traceback.format_exc()}"
                                    system_console.log(
                                        f"Error parsing tool {tool_name}"
                                    )
                                    tool_results.append(
                                        ToolResultBlockParam(
                                            type="tool_result",
                                            tool_use_id=str(tc["id"]),
                                            content=error_msg,
                                            is_error=True,
                                        )
                                    )
                                    continue

                                system_console.print(
                                    f"\n---------------------------------------\n# Assistant invoked tool: {tool_parsed}"
                                )

                                try:
                                    output_or_dones, _ = get_tool_output(
                                        context,
                                        tool_parsed,
                                        default_enc,
                                        limit - cost,
                                        loop,
                                        max_tokens=8000,
                                    )
                                except Exception as e:
                                    output_or_dones = [
                                        (
                                            f"GOT EXCEPTION while calling tool. Error: {e}"
                                        )
                                    ]
                                    tb = traceback.format_exc()
                                    error_console.print(
                                        str(output_or_dones) + "\n" + tb
                                    )

                                tool_results_content: list[
                                    TextBlockParam | ImageBlockParam
                                ] = []
                                for output in output_or_dones:
                                    if isinstance(output, ImageData):
                                        tool_results_content.append(
                                            {
                                                "type": "image",
                                                "source": {
                                                    "type": "base64",
                                                    "media_type": output.media_type,
                                                    "data": output.data,
                                                },
                                            }
                                        )

                                    else:
                                        tool_results_content.append(
                                            {
                                                "type": "text",
                                                "text": output,
                                            },
                                        )
                                tool_results.append(
                                    ToolResultBlockParam(
                                        type="tool_result",
                                        tool_use_id=str(tc["id"]),
                                        content=tool_results_content,
                                    )
                                )
                            else:
                                _histories.append(
                                    {
                                        "role": "assistant",
                                        "content": full_response
                                        if full_response.strip()
                                        else "...",
                                    }  # Fixes anthropic issue of non empty response only
                                )

            except KeyboardInterrupt:
                waiting_for_assistant = False
                input("Interrupted...enter to redo the current turn")
            else:
                history.extend(_histories)
                if tool_results:
                    history.append({"role": "user", "content": tool_results})
                    waiting_for_assistant = True
                save_history(history, session_id)

    return "Couldn't finish the task", cost


if __name__ == "__main__":
    app()
