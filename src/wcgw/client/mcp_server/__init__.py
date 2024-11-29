# mypy: disable-error-code="import-untyped"
from wcgw.client.mcp_server import server
import asyncio
from typer import Typer

main = Typer()


@main.command()
def app(computer_use: bool = False) -> None:
    """Main entry point for the package."""
    asyncio.run(server.main(computer_use))


# Optionally expose other important items at package level
__all__ = ["main", "server"]
