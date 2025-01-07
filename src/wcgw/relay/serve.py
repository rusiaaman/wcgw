import asyncio
import threading
import time
from importlib import metadata
from typing import Any, Callable, Coroutine, DefaultDict, Optional
from uuid import UUID

import fastapi
import semantic_version  # type: ignore[import-untyped]
import uvicorn
from dotenv import load_dotenv
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..types_ import (
    BashCommand,
    BashInteraction,
    ContextSave,
    FileEdit,
    FileEditFindReplace,
    Initialize,
    ReadFiles,
    ResetShell,
    WriteIfEmpty,
)


class Mdata(BaseModel):
    data: (
        BashCommand
        | BashInteraction
        | WriteIfEmpty
        | ResetShell
        | FileEditFindReplace
        | FileEdit
        | ReadFiles
        | Initialize
        | ContextSave
        | str
    )
    user_id: UUID


app = fastapi.FastAPI()

clients: dict[UUID, Callable[[Mdata], Coroutine[None, None, None]]] = {}
websockets: dict[UUID, WebSocket] = {}
gpts: dict[UUID, Callable[[str], None]] = {}

images: DefaultDict[UUID, dict[str, dict[str, Any]]] = DefaultDict(dict)


CLIENT_VERSION_MINIMUM = "2.7.0"


@app.websocket("/v1/register/{uuid}")
async def register_websocket(websocket: WebSocket, uuid: UUID) -> None:
    await websocket.accept()

    # send server version
    version = metadata.version("wcgw")
    await websocket.send_text(version)

    # receive client version
    client_version = await websocket.receive_text()
    sem_version_client = semantic_version.Version.coerce(client_version)
    sem_version_server = semantic_version.Version.coerce(CLIENT_VERSION_MINIMUM)
    if sem_version_client < sem_version_server:
        await websocket.send_text(
            Mdata(
                user_id=uuid,
                data=f"Client version {client_version} is outdated. Please upgrade to {CLIENT_VERSION_MINIMUM} or higher.",
            ).model_dump_json()
        )
        await websocket.close(
            reason="Client version outdated. Please upgrade to the latest version.",
            code=1002,
        )
        return

    # Register the callback for this client UUID
    async def send_data_callback(data: Mdata) -> None:
        await websocket.send_text(data.model_dump_json())

    clients[uuid] = send_data_callback
    websockets[uuid] = websocket

    try:
        while True:
            received_data = await websocket.receive_text()
            if uuid not in gpts:
                raise fastapi.HTTPException(status_code=400, detail="No call made")
            gpts[uuid](received_data)
    except WebSocketDisconnect:
        # Remove the client if the WebSocket is disconnected
        del clients[uuid]
        del websockets[uuid]
        print(f"Client {uuid} disconnected")


class WriteIfEmptyWithUUID(WriteIfEmpty):
    user_id: UUID


@app.post("/v1/create_file")
async def create_file(write_file_data: WriteIfEmptyWithUUID) -> str:
    user_id = write_file_data.user_id
    if user_id not in clients:
        return "Failure: id not found, ask the user to check it."

    results: Optional[str] = None

    def put_results(result: str) -> None:
        nonlocal results
        results = result

    gpts[user_id] = put_results

    await clients[user_id](Mdata(data=write_file_data, user_id=user_id))

    start_time = time.time()
    while time.time() - start_time < 30:
        if results is not None:
            return results
        await asyncio.sleep(0.1)

    raise fastapi.HTTPException(status_code=500, detail="Timeout error")


class FileEditWithUUID(FileEdit):
    user_id: UUID


@app.post("/v1/full_file_edit")
async def file_edit_find_replace(
    file_edit_find_replace: FileEditWithUUID,
) -> str:
    user_id = file_edit_find_replace.user_id
    if user_id not in clients:
        return "Failure: id not found, ask the user to check it."

    results: Optional[str] = None

    def put_results(result: str) -> None:
        nonlocal results
        results = result

    gpts[user_id] = put_results

    await clients[user_id](
        Mdata(
            data=file_edit_find_replace,
            user_id=user_id,
        )
    )

    start_time = time.time()
    while time.time() - start_time < 30:
        if results is not None:
            return results
        await asyncio.sleep(0.1)

    raise fastapi.HTTPException(status_code=500, detail="Timeout error")


class ResetShellWithUUID(ResetShell):
    user_id: UUID


@app.post("/v1/reset_shell")
async def reset_shell(reset_shell: ResetShellWithUUID) -> str:
    user_id = reset_shell.user_id
    if user_id not in clients:
        return "Failure: id not found, ask the user to check it."

    results: Optional[str] = None

    def put_results(result: str) -> None:
        nonlocal results
        results = result

    gpts[user_id] = put_results

    await clients[user_id](Mdata(data=reset_shell, user_id=user_id))

    start_time = time.time()
    while time.time() - start_time < 30:
        if results is not None:
            return results
        await asyncio.sleep(0.1)

    raise fastapi.HTTPException(status_code=500, detail="Timeout error")


class CommandWithUUID(BaseModel):
    command: str
    user_id: UUID


@app.post("/v1/bash_command")
async def bash_command(command: CommandWithUUID) -> str:
    user_id = command.user_id
    if user_id not in clients:
        return "Failure: id not found, ask the user to check it."

    results: Optional[str] = None

    def put_results(result: str) -> None:
        nonlocal results
        results = result

    gpts[user_id] = put_results

    await clients[user_id](
        Mdata(data=BashCommand(command=command.command), user_id=user_id)
    )

    start_time = time.time()
    while time.time() - start_time < 30:
        if results is not None:
            return results
        await asyncio.sleep(0.1)

    raise fastapi.HTTPException(status_code=500, detail="Timeout error")


class BashInteractionWithUUID(BashInteraction):
    user_id: UUID


@app.post("/v1/bash_interaction")
async def bash_interaction(bash_interaction: BashInteractionWithUUID) -> str:
    user_id = bash_interaction.user_id
    if user_id not in clients:
        return "Failure: id not found, ask the user to check it."

    results: Optional[str] = None

    def put_results(result: str) -> None:
        nonlocal results
        results = result

    gpts[user_id] = put_results

    await clients[user_id](
        Mdata(
            data=bash_interaction,
            user_id=user_id,
        )
    )

    start_time = time.time()
    while time.time() - start_time < 30:
        if results is not None:
            return results
        await asyncio.sleep(0.1)

    raise fastapi.HTTPException(status_code=500, detail="Timeout error")


class ReadFileWithUUID(ReadFiles):
    user_id: UUID


@app.post("/v1/read_file")
async def read_file_endpoint(read_file_data: ReadFileWithUUID) -> str:
    user_id = read_file_data.user_id
    if user_id not in clients:
        return "Failure: id not found, ask the user to check it."

    results: Optional[str] = None

    def put_results(result: str) -> None:
        nonlocal results
        results = result

    gpts[user_id] = put_results

    await clients[user_id](Mdata(data=read_file_data, user_id=user_id))

    start_time = time.time()
    while time.time() - start_time < 30:
        if results is not None:
            return results
        await asyncio.sleep(0.1)

    raise fastapi.HTTPException(status_code=500, detail="Timeout error")


class InitializeWithUUID(Initialize):
    user_id: UUID


@app.post("/v1/initialize")
async def initialize(initialize_data: InitializeWithUUID) -> str:
    user_id = initialize_data.user_id
    if user_id not in clients:
        return "Failure: id not found, ask the user to check it."

    results: Optional[str] = None

    def put_results(result: str) -> None:
        nonlocal results
        results = result

    gpts[user_id] = put_results

    await clients[user_id](Mdata(data=initialize_data, user_id=user_id))

    start_time = time.time()
    while time.time() - start_time < 30:
        if results is not None:
            return results
        await asyncio.sleep(0.1)

    raise fastapi.HTTPException(status_code=500, detail="Timeout error")


class ContextSaveWithUUID(ContextSave):
    user_id: UUID


@app.post("/v1/context_save")
async def context_save(context_save_data: ContextSaveWithUUID) -> str:
    user_id = context_save_data.user_id
    if user_id not in clients:
        return "Failure: id not found, ask the user to check it."

    results: Optional[str] = None

    def put_results(result: str) -> None:
        nonlocal results
        results = result

    gpts[user_id] = put_results

    await clients[user_id](Mdata(data=context_save_data, user_id=user_id))

    start_time = time.time()
    while time.time() - start_time < 30:
        if results is not None:
            return results
        await asyncio.sleep(0.1)

    raise fastapi.HTTPException(status_code=500, detail="Timeout error")


app.mount("/static", StaticFiles(directory="static"), name="static")


def run() -> None:
    load_dotenv()

    uvicorn_thread = threading.Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={
            "host": "0.0.0.0",
            "port": 8000,
            "log_level": "info",
            "access_log": True,
        },
    )
    uvicorn_thread.start()
    uvicorn_thread.join()


if __name__ == "__main__":
    run()
