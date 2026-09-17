import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from importlib import metadata
from typing import Any, AsyncIterator

import mcp.server.stdio
import mcp.types as types
import uvicorn
from fastapi import FastAPI
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyUrl

from wcgw.client.modes import KTS
from wcgw.client.tool_prompts import TOOL_PROMPTS

from ...types_ import (
    BashCommand,
    ContextSave,
    FileWriteOrEdit,
    Initialize,
    ReadFiles,
    ReadImage,
)
from ..bash_state.bash_state import (
    CONFIG,
    BashState,
    get_bash_state_dir_xdg,
    get_tmpdir,
)
from ..tools import (
    TOOLS,
    Context,
    get_tool_output,
    parse_tool_by_name,
    which_tool_name,
)

server: Server[Any] = Server("wcgw")

# Log only time stamp
logging.basicConfig(level=logging.INFO, format="%(asctime)s: %(message)s")
logger = logging.getLogger("wcgw")


class Console:
    def print(self, msg: str, *args: Any, **kwargs: Any) -> None:
        logger.info(msg)

    def log(self, msg: str, *args: Any, **kwargs: Any) -> None:
        logger.info(msg)


@server.list_resources()  # type: ignore
async def handle_list_resources() -> list[types.Resource]:
    return []


@server.read_resource()  # type: ignore
async def handle_read_resource(uri: AnyUrl) -> str:
    raise ValueError("No resources available")


PROMPTS = {
    "KnowledgeTransfer": (
        types.Prompt(
            name="KnowledgeTransfer",
            description="Prompt for invoking ContextSave tool in order to do a comprehensive knowledge transfer of a coding task. Prompts to save detailed error log and instructions.",
        ),
        KTS,
    )
}


@server.list_prompts()  # type: ignore
async def handle_list_prompts() -> list[types.Prompt]:
    return [x[0] for x in PROMPTS.values()]


@server.get_prompt()  # type: ignore
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    assert BASH_STATE
    messages = [
        types.PromptMessage(
            role="user",
            content=types.TextContent(
                type="text", text=PROMPTS[name][1][BASH_STATE.mode]
            ),
        )
    ]
    return types.GetPromptResult(messages=messages)


@server.list_tools()  # type: ignore
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """

    return TOOL_PROMPTS


@server.call_tool()  # type: ignore
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    global BASH_STATE
    if not arguments:
        raise ValueError("Missing arguments")

    tool_type = which_tool_name(name)
    tool_call = parse_tool_by_name(name, arguments)

    async with leased_state_for_tool(tool_call) as state:
        try:
            if isinstance(tool_call, FileWriteOrEdit):
                sync_legacy_whitelist_into_state(state)
            async with state_call_lock(state.current_thread_id):
                output_or_dones, _ = await asyncio.to_thread(
                    get_tool_output,
                    Context(state, state.console),
                    tool_call,
                    0.0,
                    lambda x, y: ("", 0),
                    24000,  # coding_max_tokens
                    8000,  # noncoding_max_tokens
                )

        except Exception as e:
            output_or_dones = [f"GOT EXCEPTION while calling tool. Error: {e}"]

    content: list[types.TextContent | types.ImageContent | types.EmbeddedResource] = []
    for output_or_done in output_or_dones:
        if isinstance(output_or_done, str):
            if issubclass(tool_type, Initialize):
                # Prepare the original hardcoded message
                original_message = """
- Additional important note: as soon as you encounter "The user has chosen to disallow the tool call.", immediately stop doing everything and ask user for the reason.

Initialize call done.
    """

                # If custom instructions exist, prepend them to the original message
                if CUSTOM_INSTRUCTIONS:
                    output_or_done += f"\n{CUSTOM_INSTRUCTIONS}\n{original_message}"
                else:
                    output_or_done += original_message

            content.append(types.TextContent(type="text", text=output_or_done))
        else:
            content.append(
                types.ImageContent(
                    type="image",
                    data=output_or_done.data,
                    mimeType=output_or_done.media_type,
                )
            )

    return content


BASH_STATE: BashState | None = None
BASH_STATES: dict[str, BashState] = {}
STATE_CALL_LOCKS: dict[str, asyncio.Lock] = {}
STATE_CREATION_LOCKS: dict[str, asyncio.Lock] = {}
STATE_ACTIVE_CALLS: dict[str, int] = {}
CUSTOM_INSTRUCTIONS = None
STARTING_DIR = ""
SHELL_PATH = ""


def state_call_lock(thread_id: str) -> asyncio.Lock:
    lock = STATE_CALL_LOCKS.get(thread_id)
    if lock is None:
        lock = asyncio.Lock()
        STATE_CALL_LOCKS[thread_id] = lock
    return lock


def state_creation_lock(thread_id: str) -> asyncio.Lock:
    lock = STATE_CREATION_LOCKS.get(thread_id)
    if lock is None:
        lock = asyncio.Lock()
        STATE_CREATION_LOCKS[thread_id] = lock
    return lock


def new_state(thread_id: str | None) -> BashState:
    return BashState(
        Console(),
        STARTING_DIR,
        None,
        None,
        None,
        None,
        True,
        None,
        thread_id,
        SHELL_PATH or None,
    )


def tool_thread_id(tool_call: TOOLS) -> str:
    if isinstance(tool_call, BashCommand):
        return tool_call.action_json.thread_id
    if isinstance(
        tool_call,
        (Initialize, FileWriteOrEdit, ReadFiles, ReadImage, ContextSave),
    ):
        return tool_call.thread_id
    raise TypeError(f"Unsupported tool type: {type(tool_call)}")


def sync_legacy_whitelist_into_state(state: BashState) -> None:
    if BASH_STATE is not None and BASH_STATE is not state:
        state.whitelist_for_overwrite.update(BASH_STATE.whitelist_for_overwrite)


def restored_state(thread_id: str) -> BashState | None:
    state = new_state(None)
    if state.load_state_from_thread_id(thread_id):
        return state
    state.cleanup()
    return None


async def state_for_tool(tool_call: TOOLS) -> BashState:
    if isinstance(tool_call, Initialize) and tool_call.type == "first_call":
        new = await asyncio.to_thread(new_state, None)
        BASH_STATES[new.current_thread_id] = new
        return new

    thread_id = tool_thread_id(tool_call)
    if not thread_id:
        if BASH_STATE is None:
            raise RuntimeError("WCGW server state is not configured")
        return BASH_STATE

    existing = BASH_STATES.get(thread_id)
    if existing is not None:
        return existing

    async with state_creation_lock(thread_id):
        existing = BASH_STATES.get(thread_id)
        if existing is not None:
            return existing

        restored = await asyncio.to_thread(restored_state, thread_id)
        if restored is None:
            raise ValueError(
                f"No saved WCGW state exists for thread_id `{thread_id}`; initialize it first"
            )
        sync_legacy_whitelist_into_state(restored)
        BASH_STATES[thread_id] = restored
        return restored


@asynccontextmanager
async def leased_state_for_tool(tool_call: TOOLS) -> AsyncIterator[BashState]:
    state = await state_for_tool(tool_call)
    leased_thread_id = state.current_thread_id
    STATE_ACTIVE_CALLS[leased_thread_id] = (
        STATE_ACTIVE_CALLS.get(leased_thread_id, 0) + 1
    )
    try:
        yield state
    finally:
        active_calls = STATE_ACTIVE_CALLS.get(leased_thread_id, 0)
        if active_calls <= 1:
            STATE_ACTIVE_CALLS.pop(leased_thread_id, None)
        else:
            STATE_ACTIVE_CALLS[leased_thread_id] = active_calls - 1

        current_thread_id = state.current_thread_id
        if current_thread_id != leased_thread_id:
            if BASH_STATES.get(leased_thread_id) is state:
                BASH_STATES.pop(leased_thread_id)
            BASH_STATES[current_thread_id] = state
            STATE_CALL_LOCKS.pop(leased_thread_id, None)
            STATE_CREATION_LOCKS.pop(leased_thread_id, None)


HTTP_STATE_IDLE_TIMEOUT_ENV = "WCGW_HTTP_STATE_IDLE_TIMEOUT_SECONDS"
DEFAULT_HTTP_STATE_IDLE_TIMEOUT_SECONDS = 60.0 * 60.0
HTTP_STATE_REAPER_INTERVAL_SECONDS = 60.0


def http_state_idle_timeout_seconds() -> float:
    configured = os.getenv(HTTP_STATE_IDLE_TIMEOUT_ENV)
    if configured is None:
        return DEFAULT_HTTP_STATE_IDLE_TIMEOUT_SECONDS
    try:
        idle_timeout_seconds = float(configured)
    except ValueError:
        logger.warning(
            "%s must be a non-negative number; using %.0f seconds",
            HTTP_STATE_IDLE_TIMEOUT_ENV,
            DEFAULT_HTTP_STATE_IDLE_TIMEOUT_SECONDS,
        )
        return DEFAULT_HTTP_STATE_IDLE_TIMEOUT_SECONDS
    if idle_timeout_seconds < 0:
        logger.warning(
            "%s must be non-negative; using %.0f seconds",
            HTTP_STATE_IDLE_TIMEOUT_ENV,
            DEFAULT_HTTP_STATE_IDLE_TIMEOUT_SECONDS,
        )
        return DEFAULT_HTTP_STATE_IDLE_TIMEOUT_SECONDS
    return idle_timeout_seconds


def state_last_saved_at(thread_id: str) -> float | None:
    state_file = os.path.join(
        get_bash_state_dir_xdg(), f"{thread_id}_bash_state.json"
    )
    try:
        return os.path.getmtime(state_file)
    except OSError:
        return None


def state_can_be_reaped(
    thread_id: str, state: BashState, now: float, idle_timeout_seconds: float
) -> bool:
    if state is BASH_STATE:
        return False
    if STATE_ACTIVE_CALLS.get(thread_id, 0) > 0:
        return False
    last_saved_at = state_last_saved_at(thread_id)
    if last_saved_at is not None and now - last_saved_at < idle_timeout_seconds:
        return False
    return not state.has_running_commands()


async def reap_idle_states(now: float, idle_timeout_seconds: float) -> int:
    if idle_timeout_seconds <= 0:
        return 0

    reaped: list[tuple[str, BashState]] = []
    for thread_id, state in list(BASH_STATES.items()):
        if not state_can_be_reaped(thread_id, state, now, idle_timeout_seconds):
            continue
        if BASH_STATES.pop(thread_id, None) is not state:
            continue
        STATE_CALL_LOCKS.pop(thread_id, None)
        STATE_CREATION_LOCKS.pop(thread_id, None)
        STATE_ACTIVE_CALLS.pop(thread_id, None)
        reaped.append((thread_id, state))

    if not reaped:
        return 0

    cleanup_results = await asyncio.gather(
        *(asyncio.to_thread(state.cleanup) for _, state in reaped),
        return_exceptions=True,
    )
    for (thread_id, _), result in zip(reaped, cleanup_results):
        if isinstance(result, BaseException):
            logger.error(
                "failed to clean up idle WCGW shell state %s: %s",
                thread_id,
                result,
            )
    logger.info("reaped %d idle WCGW shell states", len(reaped))
    return len(reaped)


async def reap_idle_states_forever(idle_timeout_seconds: float) -> None:
    while True:
        await asyncio.sleep(HTTP_STATE_REAPER_INTERVAL_SECONDS)
        await reap_idle_states(time.time(), idle_timeout_seconds)


def configure_server(shell_path: str) -> str:
    global BASH_STATE, CUSTOM_INSTRUCTIONS, STARTING_DIR, SHELL_PATH
    CONFIG.update(3, 55, 5)
    version = str(metadata.version("wcgw"))
    CUSTOM_INSTRUCTIONS = os.getenv("WCGW_SERVER_INSTRUCTIONS")
    STARTING_DIR = os.path.join(get_tmpdir(), "claude_playground")
    SHELL_PATH = shell_path
    BASH_STATE = BashState(
        Console(),
        STARTING_DIR,
        None,
        None,
        None,
        None,
        True,
        None,
        None,
        SHELL_PATH or None,
    )
    BASH_STATE.console.log("wcgw version: " + version)
    return version


def cleanup_states() -> None:
    global BASH_STATE
    states = {
        id(state): state
        for state in [BASH_STATE, *BASH_STATES.values()]
        if state is not None
    }
    for state in states.values():
        try:
            state.cleanup()
        except Exception:
            logger.exception("failed to clean up WCGW shell state")
    BASH_STATES.clear()
    STATE_CALL_LOCKS.clear()
    STATE_CREATION_LOCKS.clear()
    STATE_ACTIVE_CALLS.clear()
    BASH_STATE = None


async def main(shell_path: str = "") -> None:
    version = configure_server(shell_path)
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="wcgw",
                    server_version=version,
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
                raise_exceptions=False,
            )
    finally:
        cleanup_states()


def streamable_http_app(shell_path: str, host: str, port: int) -> FastAPI:
    configure_server(shell_path)
    security_settings = TransportSecuritySettings(
        allowed_hosts=[host, f"{host}:{port}", "localhost", f"localhost:{port}"],
        allowed_origins=[],
    )
    session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        json_response=False,
        stateless=True,
        security_settings=security_settings,
        retry_interval=None,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        idle_timeout_seconds = http_state_idle_timeout_seconds()
        reaper_task: asyncio.Task[None] | None = None
        if idle_timeout_seconds > 0:
            reaper_task = asyncio.create_task(
                reap_idle_states_forever(idle_timeout_seconds)
            )
        try:
            async with session_manager.run():
                yield
        finally:
            if reaper_task is not None:
                reaper_task.cancel()
                try:
                    await reaper_task
                except asyncio.CancelledError:
                    pass
            cleanup_states()

    app = FastAPI(lifespan=lifespan)
    app.mount("/mcp", session_manager.handle_request)
    return app


def run_streamable_http(shell_path: str, host: str, port: int) -> None:
    app = streamable_http_app(shell_path, host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
