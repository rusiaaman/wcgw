# mypy: disable-error-code="import-untyped"
import asyncio
from importlib import metadata
from typing import Literal

import typer
from typer import Typer

from wcgw.client.mcp_server import server

main = Typer()


@main.command()
def app(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit"
    ),
    shell: str = typer.Option(
        "", "--shell", help="Path to shell executable (defaults to $SHELL or /bin/bash)"
    ),
    transport: Literal["stdio", "streamable-http"] = typer.Option(
        "stdio", "--transport", help="MCP transport to serve"
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Bind host for Streamable HTTP"
    ),
    port: int = typer.Option(8765, "--port", help="Bind port for Streamable HTTP"),
) -> None:
    """Main entry point for the package."""
    if version:
        version_ = metadata.version("wcgw")
        print(f"wcgw version: {version_}")
        raise typer.Exit()

    if transport == "stdio":
        asyncio.run(server.main(shell))
    else:
        server.run_streamable_http(shell, host, port)


# Optionally expose other important items at package level
__all__ = ["main", "server"]
