# Claude desktop support

## Setup

Update `claude_desktop_config.json`

```json
{
  "mcpServers": {
    "wcgw": {
      "command": "uvx",
      "args": ["--from", "wcgw", "wcgw_mcp"]
    }
  }
}
```

Then restart claude app.

## Usage

You should be able to see this icon if everything goes right.

![mcp icon](https://github.com/rusiaaman/wcgw/blob/main/static/rocket-icon.png?raw=true)

Then ask claude to execute shell commands, read files, edit files, run your code, etc.
