from .client.mcp_server import main as mcp_server
from .client.mcp_server.fastmcp_server import mcp as fastmcp_server_instance

# Export mcp_server as the default entry point for wcgw
listen = mcp_server

# FastMCP server entry point
def fastmcp_server():
    import sys
    
    # Check for transport argument
    transport = "http"  # Default to HTTP for remote access
    host = "0.0.0.0"    # Listen on all interfaces
    port = 8000
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--stdio":
            transport = "stdio"
        elif sys.argv[1] == "--help":
            print("Usage: wcgw_fastmcp [--stdio]")
            print("  --stdio: Use stdio transport (default is HTTP)")
            sys.exit(0)
    
    # Run the server
    if transport == "stdio":
        fastmcp_server_instance.run()
    else:
        print(f"Starting FastMCP server on http://{host}:{port}/mcp")
        fastmcp_server_instance.run(
            transport="http",
            host=host,
            port=port,
            path="/mcp"
        )
