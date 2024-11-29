# Claude desktop support

`wcgw` enables Claude desktop app on Mac to access shell and file system in order to automate tasks, run code, etc.

It also has a computer use feature to connect to linux running on docker. Claude can fully control it including mouse and keyboard.

## Setup

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

## Example

### Computer use example

![computer-use](https://github.com/rusiaaman/wcgw/blob/main/static/computer-use.jpg?raw=true)

### Shell example

![example](https://github.com/rusiaaman/wcgw/blob/main/static/example.jpg?raw=true)
