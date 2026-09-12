import asyncio
import os
import re
import shutil

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from wcgw.client.mcp_server import server


def result_text(result) -> str:
    return "\n".join(getattr(item, "text", "") for item in result.content)


@pytest.mark.asyncio
async def test_stdio_transport_keeps_conversation_shells_concurrent(tmp_path) -> None:
    executable = shutil.which("wcgw_mcp")
    assert executable is not None
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/bash"
    env["XDG_STATE_HOME"] = str(tmp_path / "state")

    params = StdioServerParameters(
        command=executable,
        args=["--shell", "/bin/bash"],
        env=env,
        cwd=str(tmp_path),
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            init_args = {
                "type": "first_call",
                "any_workspace_path": "",
                "initial_files_to_read": [],
                "task_id_to_resume": "",
                "mode_name": "wcgw",
                "thread_id": "",
            }
            first_init, second_init = await asyncio.gather(
                session.call_tool("Initialize", init_args),
                session.call_tool("Initialize", init_args),
            )
            first_match = re.search(r"Use thread_id=(\w+)", result_text(first_init))
            second_match = re.search(r"Use thread_id=(\w+)", result_text(second_init))
            assert first_match is not None
            assert second_match is not None
            first_thread = first_match.group(1)
            second_thread = second_match.group(1)
            assert first_thread != second_thread

            # Warm both shells so shell startup time is not part of the concurrency assertion.
            await asyncio.gather(
                session.call_tool(
                    "BashCommand",
                    {
                        "type": "command",
                        "command": "pwd",
                        "thread_id": first_thread,
                        "wait_for_seconds": 0.5,
                    },
                ),
                session.call_tool(
                    "BashCommand",
                    {
                        "type": "command",
                        "command": "pwd",
                        "thread_id": second_thread,
                        "wait_for_seconds": 0.5,
                    },
                ),
            )

            long_call = asyncio.create_task(
                session.call_tool(
                    "BashCommand",
                    {
                        "type": "command",
                        "command": "sleep 1",
                        "thread_id": first_thread,
                        "wait_for_seconds": 2,
                    },
                )
            )
            await asyncio.sleep(0.02)
            short_call = asyncio.create_task(
                session.call_tool(
                    "BashCommand",
                    {
                        "type": "command",
                        "command": "pwd",
                        "thread_id": second_thread,
                        "wait_for_seconds": 0.5,
                    },
                )
            )
            short_result = await asyncio.wait_for(short_call, timeout=2)
            assert "status = process exited" in result_text(short_result)
            assert not long_call.done()

            long_result = await asyncio.wait_for(long_call, timeout=2)
            assert "status = process exited" in result_text(long_result)


@pytest.mark.asyncio
async def test_streamable_http_transport_serves_wcgw(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    app = server.streamable_http_app("/bin/bash", "localhost", 8765)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://localhost:8765"
        ) as http_client:
            async with streamable_http_client(
                "http://localhost:8765/mcp/", http_client=http_client
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    initialized = await session.call_tool(
                        "Initialize",
                        {
                            "type": "first_call",
                            "any_workspace_path": "",
                            "initial_files_to_read": [],
                            "task_id_to_resume": "",
                            "mode_name": "wcgw",
                            "thread_id": "",
                        },
                    )
                    match = re.search(r"Use thread_id=(\w+)", result_text(initialized))
                    assert match is not None
                    first_thread = match.group(1)
                    second_initialized = await session.call_tool(
                        "Initialize",
                        {
                            "type": "first_call",
                            "any_workspace_path": "",
                            "initial_files_to_read": [],
                            "task_id_to_resume": "",
                            "mode_name": "wcgw",
                            "thread_id": "",
                        },
                    )
                    second_match = re.search(
                        r"Use thread_id=(\w+)", result_text(second_initialized)
                    )
                    assert second_match is not None
                    second_thread = second_match.group(1)
                    assert second_thread != first_thread

                    await asyncio.gather(
                        session.call_tool(
                            "BashCommand",
                            {
                                "type": "command",
                                "command": "pwd",
                                "thread_id": first_thread,
                                "wait_for_seconds": 0.5,
                            },
                        ),
                        session.call_tool(
                            "BashCommand",
                            {
                                "type": "command",
                                "command": "pwd",
                                "thread_id": second_thread,
                                "wait_for_seconds": 0.5,
                            },
                        ),
                    )
                    long_call = asyncio.create_task(
                        session.call_tool(
                            "BashCommand",
                            {
                                "type": "command",
                                "command": "sleep 1",
                                "thread_id": first_thread,
                                "wait_for_seconds": 2,
                            },
                        )
                    )
                    await asyncio.sleep(0.02)
                    short_result = await asyncio.wait_for(
                        session.call_tool(
                            "BashCommand",
                            {
                                "type": "command",
                                "command": "pwd",
                                "thread_id": second_thread,
                                "wait_for_seconds": 0.5,
                            },
                        ),
                        timeout=2,
                    )
                    assert "status = process exited" in result_text(short_result)
                    assert not long_call.done()
                    long_result = await asyncio.wait_for(long_call, timeout=2)
                    assert "status = process exited" in result_text(long_result)
