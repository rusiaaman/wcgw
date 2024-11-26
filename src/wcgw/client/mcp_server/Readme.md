# Claude desktop support

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

Computer use is enabled by default. Claude will be able to connect to any docker container with linux environment. Native system control isn't supported outside docker.

First run a sample docker image with desktop and optionally VNC connection:

```sh
docker run \
    --entrypoint "" \
    -p 6080:6080 \
    -e WIDTH=1024 \
    -e HEIGHT=768 \
    -d \
    ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest \
    bash -c "\
        ./start_all.sh && \
        ./novnc_startup.sh && \
        python http_server.py > /tmp/server_logs.txt 2>&1 & \
        tail -f /dev/null"
```

Connect to `http://localhost:6080/vnc.html` for desktop view (VNC) of the system running in the docker. Then ask claude to control the docker os.

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
