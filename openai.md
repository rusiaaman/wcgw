# ChatGPT Integration Guide

## 🪜 Steps:

1. Run a relay server with a domain name and https support (or use ngrok) use the instructions in next section.
2. Create a custom gpt that connects to the relay server, instructions in next sections.
3. Run the client in any directory of choice. `uvx wcgw@latest`
4. The custom GPT can now run any command on your terminal

## Creating the relay server

### If you've a domain name and ssl certificate

Run the server
`gunicorn --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:443 src.wcgw.relay.serve:app  --certfile fullchain.pem  --keyfile  privkey.pem`

If you don't have public ip and domain name, you can use `ngrok` or similar services to get a https address to the api.

Then specify the server url in the `wcgw` command like so:
`uv tool run --python 3.12 wcgw@latest --server-url wss://your-url/v1/register`

### Using ngrok

Run the server
`uv tool run --python 3.12 --from wcgw@latest wcgw_relay`

This will start an uvicorn server on port 8000. You can use ngrok to get a public address to the server.

`ngrok http 8000`

Then specify the ngrok address in the `wcgw` command like so:
`uv tool run --python 3.12 wcgw@latest --server-url wss://4900-1c2c-6542-b922-a596-f8f8.ngrok-free.app/v1/register`

## Creating the custom gpt

I've used the following instructions and action json schema to create the custom GPT. (Replace wcgw.arcfu.com with the address to your server)

https://github.com/rusiaaman/wcgw/blob/main/gpt_instructions.txt
https://github.com/rusiaaman/wcgw/blob/main/gpt_action_json_schema.json

### Chat

Let the chatgpt know your user id in any format. E.g., "user_id=<your uuid>" followed by rest of your instructions.

### How it works on chatgpt app?

Your commands are relayed through a server to the terminal client.

Chatgpt sends a request to the relay server using the user id that you share with it. The relay server holds a websocket with the terminal client against the user id and acts as a proxy to pass the request.

It's secure in both the directions. Either a malicious actor or a malicious Chatgpt has to correctly guess your UUID for any security breach.

## Showcase

### Unit tests and github actions

[The first version of unit tests and github workflow to test on multiple python versions were written by the custom chatgpt](https://chatgpt.com/share/6717f922-8998-8005-b825-45d4b348b4dd)

### Create a todo app using react + typescript + vite

![Screenshot](https://github.com/rusiaaman/wcgw/blob/main/static/ss1.png?raw=true)

## Local shell access with OpenAI API key

Add `OPENAI_API_KEY` and `OPENAI_ORG_ID` env variables.

Then run:

`uvx --from wcgw@latest wcgw_local  --limit 0.1` # Cost limit $0.1

You can now directly write messages or press enter key to open vim for multiline message and text pasting.
