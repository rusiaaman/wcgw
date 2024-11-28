# Shell and Coding agent on Chatgpt and Claude desktop apps

- An MCP server on claude desktop for autonomous shell, coding and desktop control agent.
- A custom gpt on chatgpt web/desktop apps to interact with your local shell, edit files, run code, etc.


[![Tests](https://github.com/rusiaaman/wcgw/actions/workflows/python-tests.yml/badge.svg?branch=main)](https://github.com/rusiaaman/wcgw/actions/workflows/python-tests.yml)
[![Build](https://github.com/rusiaaman/wcgw/actions/workflows/python-publish.yml/badge.svg)](https://github.com/rusiaaman/wcgw/actions/workflows/python-publish.yml)

[New feature] [26-Nov-2024] Claude desktop support for shell, computer-control, coding agent.
[src/wcgw/client/mcp_server/Readme.md](src/wcgw/client/mcp_server/Readme.md)

### 🚀 Highlights

- ⚡ **Full Shell Access**: No restrictions, complete control.
- ⚡ **Desktop control on Claude**: Screen capture, mouse control, keyboard control on claude desktop (on mac with docker linux)
- ⚡ **Create, Execute, Iterate**: Ask the gpt to keep running compiler checks till all errors are fixed, or ask it to keep checking for the status of a long running command till it's done.
- ⚡ **Interactive Command Handling**: Supports interactive commands using arrow keys, interrupt, and ansi escape sequences.
- ⚡ **REPL support**: [beta] Supports python/node and other REPL execution.

## Claude
Full readme [src/wcgw/client/mcp_server/Readme.md](src/wcgw/client/mcp_server/Readme.md)
### Setup

Update `claude_desktop_config.json`

```json
{
  "mcpServers": {
    "wcgw": {
      "command": "uvx",
      "args": ["--from", "wcgw@latest", "wcgw_mcp"]
    }
  }
}
```

Then restart claude app.
You can then ask claude to execute shell commands, read files, edit files, run your code, etc.

## ChatGPT

### 🪜 Steps:

1. Run the [cli client](https://github.com/rusiaaman/wcgw?tab=readme-ov-file#client) in any directory of choice.
2. Share the generated id with this GPT: `https://chatgpt.com/g/g-Us0AAXkRh-wcgw-giving-shell-access`
3. The custom GPT can now run any command on your cli

### Client

You need to keep running this client for GPT to access your shell. Run it in a version controlled project's root.

#### Option 1: using uv [Recommended]

```sh
$ curl -LsSf https://astral.sh/uv/install.sh | sh
$ uvx wcgw@latest
```

#### Option 2: using pip

Supports python >=3.10 and <3.13

```sh
$ pip3 install wcgw
$ wcgw
```

This will print a UUID that you need to share with the gpt.

### Chat

Open the following link or search the "wcgw" custom gpt using "Explore GPTs" on chatgpt.com

https://chatgpt.com/g/g-Us0AAXkRh-wcgw-giving-shell-access

Finally, let the chatgpt know your user id in any format. E.g., "user_id=<your uuid>" followed by rest of your instructions.

NOTE: you can resume a broken connection
`wcgw --client-uuid $previous_uuid`

### How it works on chatgpt app?

Your commands are relayed through a server to the terminal client. [You could host the server on your own](https://github.com/rusiaaman/wcgw?tab=readme-ov-file#creating-your-own-custom-gpt-and-the-relay-server). For public convenience I've hosted one at https://wcgw.arcfu.com thanks to the gcloud free tier plan.

Chatgpt sends a request to the relay server using the user id that you share with it. The relay server holds a websocket with the terminal client against the user id and acts as a proxy to pass the request.

It's secure in both the directions. Either a malicious actor or a malicious Chatgpt has to correctly guess your UUID for any security breach.

# Showcase

## Claude desktop

### Resize image and move it to a new dir

![example](https://github.com/rusiaaman/wcgw/blob/main/static/example.jpg?raw=true)

## Chatgpt app

### Unit tests and github actions

[The first version of unit tests and github workflow to test on multiple python versions were written by the custom chatgpt](https://chatgpt.com/share/6717f922-8998-8005-b825-45d4b348b4dd)

### Create a todo app using react + typescript + vite

![Screenshot](https://github.com/rusiaaman/wcgw/blob/main/static/ss1.png?raw=true)

# Privacy

The relay server doesn't store any data. I can't access any information passing through it and only secure channels are used to communicate.

You may host the server on your own and create a custom gpt using the following section.

# Creating your own custom gpt and the relay server.

I've used the following instructions and action json schema to create the custom GPT. (Replace wcgw.arcfu.com with the address to your server)

https://github.com/rusiaaman/wcgw/blob/main/gpt_instructions.txt
https://github.com/rusiaaman/wcgw/blob/main/gpt_action_json_schema.json

Run the server
`gunicorn --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:443 src.wcgw.relay.serve:app  --certfile fullchain.pem  --keyfile  privkey.pem`

If you don't have public ip and domain name, you can use `ngrok` or similar services to get a https address to the api.

The specify the server url in the `wcgw` command like so
`wcgw --server-url https://your-url/v1/register`

# [Optional] Local shell access with openai API key or anthropic API key

## Openai

Add `OPENAI_API_KEY` and `OPENAI_ORG_ID` env variables.

Then run

`uvx --from wcgw@latest wcgw_local  --limit 0.1` # Cost limit $0.1

You can now directly write messages or press enter key to open vim for multiline message and text pasting.

## Anthropic

Add `ANTHROPIC_API_KEY` env variable.

Then run

`uvx --from wcgw@latest wcgw_local --claude`

You can now directly write messages or press enter key to open vim for multiline message and text pasting.
