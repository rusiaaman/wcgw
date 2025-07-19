# mypy: disable-error-code="import-untyped"
import asyncio
import importlib

import typer
from typer import Typer

from wcgw.client.mcp_server import server

main = Typer()


@main.command()
def app(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit"
    ),
) -> None:
    """Main entry point for the package."""
    if version:
        version_ = importlib.metadata.version("wcgw")
        print(f"wcgw version: {version_}")
        raise typer.Exit()

    asyncio.run(server.main())


# Optionally expose other important items at package level
__all__ = ["main", "server"]
