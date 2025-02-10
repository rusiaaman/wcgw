import importlib.metadata
import os
import time
import traceback
import uuid
from typing import Optional

import rich
import typer
import websockets
from typer import Typer
from websockets.sync.client import connect as syncconnect

from ..client.bash_state.bash_state import BashState
from ..client.tools import Context, curr_cost, default_enc, get_tool_output
from ..types_ import Mdata


def register_client(server_url: str, client_uuid: str = "") -> None:
    global default_enc, curr_cost
    # Generate a unique UUID for this client
    if not client_uuid:
        client_uuid = str(uuid.uuid4())

    # Create the WebSocket connection and context
    the_console = rich.console.Console(style="magenta", highlight=False, markup=False)
    with BashState(
        the_console, os.getcwd(), None, None, None, None, True, None
    ) as bash_state:
        context = Context(bash_state=bash_state, console=the_console)

        try:
            with syncconnect(f"{server_url}/{client_uuid}") as websocket:
                server_version = str(websocket.recv())
                print(f"Server version: {server_version}")
                client_version = importlib.metadata.version("wcgw")
                websocket.send(client_version)

                print(f"Connected. Share this user id with the chatbot: {client_uuid}")
                while True:
                    # Wait to receive data from the server
                    message = websocket.recv()
                    mdata = Mdata.model_validate_json(message)
                    if isinstance(mdata.data, str):
                        raise Exception(mdata)
                    try:
                        outputs, cost = get_tool_output(
                            context,
                            mdata.data,
                            default_enc,
                            0.0,
                            lambda x, y: ("", 0),
                            8000,
                        )
                        output = outputs[0]
                        curr_cost += cost
                        print(f"{curr_cost=}")
                    except Exception as e:
                        output = f"GOT EXCEPTION while calling tool. Error: {e}"
                        context.console.print(traceback.format_exc())
                    assert isinstance(output, str)
                    websocket.send(output)

        except (websockets.ConnectionClosed, ConnectionError, OSError):
            print(f"Connection closed for UUID: {client_uuid}, retrying")
            time.sleep(0.5)
            register_client(server_url, client_uuid)


run = Typer(pretty_exceptions_show_locals=False, no_args_is_help=True)


@run.command()
def app(
    server_url: str = "",
    client_uuid: Optional[str] = None,
    version: bool = typer.Option(False, "--version", "-v"),
) -> None:
    if version:
        version_ = importlib.metadata.version("wcgw")
        print(f"wcgw version: {version_}")
        exit()
    if not server_url:
        server_url = os.environ.get("WCGW_RELAY_SERVER", "")
        if not server_url:
            print(
                "Error: Please provide relay server url using --server_url or WCGW_RELAY_SERVER environment variable"
            )
            print(
                "\tNOTE: you need to run a relay server first, author doesn't host a relay server anymore."
            )
            print("\thttps://github.com/rusiaaman/wcgw/blob/main/openai.md")
            print("\tExample `--server-url=ws://localhost:8000/v1/register`")
            raise typer.Exit(1)
    register_client(server_url, client_uuid or "")
