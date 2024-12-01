# Shell and Coding agent for Claude and Chatgpt

- Claude - An MCP server on claude desktop for autonomous shell, coding and desktop control agent.
- Chatgpt - Allows custom gpt to talk to your shell via a relay server. 

[![Tests](https://github.com/rusiaaman/wcgw/actions/workflows/python-tests.yml/badge.svg?branch=main)](https://github.com/rusiaaman/wcgw/actions/workflows/python-tests.yml)
[![Mypy strict](https://github.com/rusiaaman/wcgw/actions/workflows/python-types.yml/badge.svg?branch=main)](https://github.com/rusiaaman/wcgw/actions/workflows/python-types.yml)
[![Build](https://github.com/rusiaaman/wcgw/actions/workflows/python-publish.yml/badge.svg)](https://github.com/rusiaaman/wcgw/actions/workflows/python-publish.yml)

## Updates

- [01 Dec 2024] Removed author hosted relay server for chatgpt.

- [26 Nov 2024] Introduced claude desktop support through mcp

## 🚀 Highlights

- ⚡ **Full Shell Access**: No restrictions, complete control.
- ⚡ **Desktop control on Claude**: Screen capture, mouse control, keyboard control on claude desktop (on mac with docker linux)
- ⚡ **Create, Execute, Iterate**: Ask claude to keep running compiler checks till all errors are fixed, or ask it to keep checking for the status of a long running command till it's done.
- ⚡ **Interactive Command Handling**: Supports interactive commands using arrow keys, interrupt, and ansi escape sequences.
- ⚡ **REPL support**: [beta] Supports python/node and other REPL execution.

## Claude Setup

Update `claude_desktop_config.json` (~/Library/Application Support/Claude/claude_desktop_config.json)

```json
{
  "mcpServers": {
    "wcgw": {
      "command": "uv",
      "args": [
        "tool",
        "run",
        "--from",
        "wcgw@latest",
        "--python",
        "3.12",
        "wcgw_mcp"
      ]
    }
  }
}
```

Then restart claude app.

### [Optional] Computer use support using desktop on docker

Computer use is disabled by default. Add `--computer-use` to enable it. This will add necessary tools to Claude including ScreenShot, Mouse and Keyboard control.

```json
{
  "mcpServers": {
    "wcgw": {
      "command": "uv",
      "args": [
        "tool",
        "run",
        "--from",
        "wcgw@latest",
        "--python",
        "3.12",
        "wcgw_mcp",
        "--computer-use"
      ]
    }
  }
}
```

Claude will be able to connect to any docker container with linux environment. Native system control isn't supported outside docker.

You'll need to run a docker image with desktop and optional VNC connection. Here's a demo image:

```sh
docker run -p 6080:6080 ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest
```

Then ask claude desktop app to control the docker os. It'll connect to the docker container and control it.

Connect to `http://localhost:6080/vnc.html` for desktop view (VNC) of the system running in the docker.

## Usage

Wait for a few seconds. You should be able to see this icon if everything goes right.

![mcp icon](https://github.com/rusiaaman/wcgw/blob/main/static/rocket-icon.png?raw=true)
over here

![mcp icon](https://github.com/rusiaaman/wcgw/blob/main/static/claude-ss.jpg?raw=true)

Then ask claude to execute shell commands, read files, edit files, run your code, etc.

If you've run the docker for LLM to access, you can ask it to control the "docker os". If you don't provide the docker container id to it, it'll try to search for available docker using `docker ps` command.


## Chatgpt Setup

Read here: https://github.com/rusiaaman/wcgw/blob/main/openai.md

## Examples

### Computer use example

![computer-use](https://github.com/rusiaaman/wcgw/blob/main/static/computer-use.jpg?raw=true)

### Shell example

![example](https://github.com/rusiaaman/wcgw/blob/main/static/example.jpg?raw=true)


## [Optional] Local shell access with openai API key or anthropic API key

### Openai

Add `OPENAI_API_KEY` and `OPENAI_ORG_ID` env variables.

Then run

`uvx --from wcgw@latest wcgw_local  --limit 0.1` # Cost limit $0.1

You can now directly write messages or press enter key to open vim for multiline message and text pasting.

### Anthropic

Add `ANTHROPIC_API_KEY` env variable.

Then run

`uvx --from wcgw@latest wcgw_local --claude`

You can now directly write messages or press enter key to open vim for multiline message and text pasting.
