import asyncio
import threading
import time
from typing import Callable, Coroutine, Literal, Optional, Sequence
from uuid import UUID
import fastapi
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import uvicorn

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


@app.post("/action")
async def chatgpt_server(json_data: Mdata) -> str:
    user_id = json_data.user_id
    if user_id not in clients:
        raise fastapi.HTTPException(
            status_code=404, detail="User with the provided id not found"
        )

    results: Optional[str] = None

    def put_results(result: str) -> None:
        nonlocal results
        results = result

    gpts[user_id] = put_results

    await clients[user_id](json_data)

    start_time = time.time()
    while time.time() - start_time < 30:
        if results is not None:
            return results
        await asyncio.sleep(0.1)

    raise fastapi.HTTPException(status_code=500, detail="Timeout error")


def run() -> None:
    load_dotenv()

    uvicorn_thread = threading.Thread(
        target=uvicorn.run, args=(app,), kwargs={"host": "0.0.0.0", "port": 8000}
    )
    uvicorn_thread.start()
    uvicorn_thread.join()


if __name__ == "__main__":
    run()
