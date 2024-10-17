import asyncio
import base64
import threading
import time
from typing import Any, Callable, Coroutine, DefaultDict, Literal, Optional, Sequence
from uuid import UUID
import fastapi
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import uvicorn
from fastapi.staticfiles import StaticFiles

from dotenv import load_dotenv


class Writefile(BaseModel):
    file_path: str
    file_content: str


Specials = Literal["Key-up", "Key-down", "Key-left", "Key-right", "Enter", "Ctrl-c"]


class ExecuteBash(BaseModel):
    execute_command: Optional[str] = None
    send_ascii: Optional[Sequence[int | Specials]] = None


class Mdata(BaseModel):
    data: ExecuteBash | Writefile
    user_id: UUID


app = fastapi.FastAPI()

clients: dict[UUID, Callable[[Mdata], Coroutine[None, None, None]]] = {}
websockets: dict[UUID, WebSocket] = {}
gpts: dict[UUID, Callable[[str], None]] = {}

images: DefaultDict[UUID, dict[str, dict[str, Any]]] = DefaultDict(dict)


@app.websocket("/register_serve_image/{uuid}")
async def register_serve_image(websocket: WebSocket, uuid: UUID) -> None:
    raise Exception("Disabled")
    await websocket.accept()
    received_data = await websocket.receive_json()
    name = received_data["name"]
    image_b64 = received_data["image_b64"]
    image_bytes = base64.b64decode(image_b64)
    images[uuid][name] = {
        "content": image_bytes,
        "media_type": received_data["media_type"],
    }


@app.get("/get_image/{uuid}/{name}")
async def get_image(uuid: UUID, name: str) -> fastapi.responses.Response:
    return fastapi.responses.Response(
        content=images[uuid][name]["content"],
        media_type=images[uuid][name]["media_type"],
    )


@app.websocket("/register/{uuid}")
async def register_websocket(websocket: WebSocket, uuid: UUID) -> None:
    await websocket.accept()

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


@app.post("/write_file")
async def write_file(write_file_data: Writefile, user_id: UUID) -> str:
    if user_id not in clients:
        raise fastapi.HTTPException(
            status_code=404, detail="User with the provided id not found"
        )

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


@app.post("/execute_bash")
async def execute_bash(excute_bash_data: ExecuteBash, user_id: UUID) -> str:
    if user_id not in clients:
        raise fastapi.HTTPException(
            status_code=404, detail="User with the provided id not found"
        )

    results: Optional[str] = None

    def put_results(result: str) -> None:
        nonlocal results
        results = result

    gpts[user_id] = put_results

    await clients[user_id](Mdata(data=excute_bash_data, user_id=user_id))

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
        target=uvicorn.run, args=(app,), kwargs={"host": "0.0.0.0", "port": 8000}
    )
    uvicorn_thread.start()
    uvicorn_thread.join()


if __name__ == "__main__":
    run()
