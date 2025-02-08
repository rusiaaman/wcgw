# mypy: disable-error-code="import-untyped"
from wcgw.client.mcp_server import server
import asyncio
from typer import Typer

main = Typer()


@main.command()
def app() -> None:
    """Main entry point for the package."""
    asyncio.run(server.main())


# Optionally expose other important items at package level
__all__ = ["main", "server"]
