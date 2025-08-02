# FastMCP Migration for WCGW

This document describes the FastMCP implementation for WCGW, enabling remote HTTP access to the shell server.

## Overview

The FastMCP implementation (`src/wcgw/client/mcp_server/fastmcp_server.py`) provides the same functionality as the original MCP server but with:

- HTTP transport support for remote access
- Cleaner decorator-based tool definitions
- Built-in support for authentication (can be added later)
- Better streaming capabilities

## Running the Server

### Local (stdio) mode:
```bash
uv run wcgw_fastmcp --stdio
```

### Remote HTTP mode (default):
```bash
uv run wcgw_fastmcp
# Server starts on http://0.0.0.0:8000/mcp
```

## Key Differences from Original MCP Server

1. **Tool Definitions**: Uses `@mcp.tool` decorators instead of manual registration
2. **Lifecycle Management**: Uses async context manager for startup/shutdown
3. **Transport**: Supports HTTP out of the box for remote access
4. **Type Hints**: Leverages Pydantic Field for parameter descriptions

## Testing

Run the test script to verify functionality:
```bash
# Start the server in one terminal
uv run wcgw_fastmcp

# In another terminal, run the test
uv run python test_fastmcp.py
```

## Security Considerations

⚠️ **WARNING**: The current implementation has NO authentication. When running on a remote server:

1. Use a firewall to restrict access
2. Add authentication before production use
3. Consider using HTTPS/TLS
4. Monitor access logs

## Next Steps

1. Add authentication using FastMCP's auth providers
2. Implement session management for multiple clients (if needed)
3. Add rate limiting
4. Set up proper logging and monitoring

## Architecture

The FastMCP server maintains the same architecture as the original:
- Single global `BASH_STATE` instance
- All 6 tools converted to FastMCP format
- Same tool logic via `get_tool_output()`

The main change is the transport layer - FastMCP handles the MCP protocol and HTTP transport, while the core WCGW logic remains unchanged.