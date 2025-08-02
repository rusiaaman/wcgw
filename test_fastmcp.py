#!/usr/bin/env python
"""Test script to verify FastMCP server functionality"""

import asyncio
from fastmcp import Client

async def test_wcgw_server():
    # Connect to the FastMCP server
    async with Client("http://localhost:8000/mcp") as client:
        print("Connected to WCGW FastMCP server")
        
        # List available tools
        tools = await client.list_tools()
        print(f"\nAvailable tools: {len(tools)}")
        for tool in tools:
            print(f"  - {tool.name}")
        
        # Test Initialize tool
        print("\n1. Testing Initialize tool...")
        result = await client.call_tool("initialize", {
            "any_workspace_path": "/tmp/test",
            "mode_name": "wcgw",
            "type": "first_call"
        })
        print(f"Initialize result: {result.content[0].text[:100]}...")
        
        # Test BashCommand tool
        print("\n2. Testing BashCommand tool...")
        result = await client.call_tool("bash_command", {
            "action_json": {"command": "pwd"}
        })
        print(f"PWD result: {result.content[0].text}")
        
        # Test ReadFiles tool
        print("\n3. Testing ReadFiles tool...")
        # First create a test file
        await client.call_tool("bash_command", {
            "action_json": {"command": "echo 'Hello from FastMCP!' > /tmp/test.txt"}
        })
        
        result = await client.call_tool("read_files", {
            "file_paths": ["/tmp/test.txt"]
        })
        print(f"File content: {result.content[0].text}")
        
        print("\nAll tests passed!")

if __name__ == "__main__":
    asyncio.run(test_wcgw_server())