# Enable shell access on chatgpt.com
A custom gpt on chatgpt web app to interact with your local shell.

### 🚀 Highlights
- ⚡ **Full Shell Access**: No restrictions, complete control.
- ⚡ **Create, Execute, Iterate**: Ask the gpt to keep running compiler checks till all errors are fixed, or ask it to keep checking for the status of a long running command till it's done.
- ⚡ **Interactive Command Handling**: [beta] Supports interactive commands using arrow keys, interrupt, and ansi escape sequences. 

###  🪜 Steps: 
1. Run the [cli client](https://github.com/rusiaaman/wcgw?tab=readme-ov-file#client) in any directory of choice.
2. Share the generated id with this GPT: `https://chatgpt.com/g/g-Us0AAXkRh-wcgw-giving-shell-access`
3. The custom GPT can now run any command on your cli

## Client

### Option 1: using pip
Supports python >=3.8 and <3.13
```sh
$ pip3 install wcgw
$ wcgw
```

### Option 2: using uv
```sh
$ curl -LsSf https://astral.sh/uv/install.sh | sh
$ uv tool run --python 3.12 wcgw
```

This will print a UUID that you need to share with the gpt.


## Chat
Open the following link or search the "wcgw" custom gpt using "Explore GPTs" on chatgpt.com

https://chatgpt.com/g/g-Us0AAXkRh-wcgw-giving-shell-access

Finally, let the chatgpt know your user id in any format. E.g., "user_id=<your uuid>" followed by rest of your instructions.

NOTE: you can resume a broken connection 
`wcgw --client-uuid $previous_uuid`

# How it works
Your commands are relayed through a server I've hosted at https://wcgw.arcfu.com. The code for that is at `src/relay/serve.py`. 

Chat gpt sends a request to the relay server using the user id that you share with it. The relay server holds a websocket with the terminal cilent against the user id and acts as a proxy to pass the request.

It's secure in both the directions. Either a malicious actor or a malicious Chatgpt has to correctly guess your UUID for any security breach. 

NOTE: the relay server doesn't store any data. If you don't trust it then you may host the server on your own and create a custom gpt. Create an issue and I'll be happy to share the full instructions and schema I've given in the custom GPT configuration. 

# Showcase

## Create a todo app using react + typescript + vite
https://chatgpt.com/share/6717d94d-756c-8005-98a6-d021c7b586aa

## Write unit tests for all files in my current repo
[Todo]


# [Optional] Local shell access with openai API key

Add `OPENAI_API_KEY` and `OPENAI_ORG_ID` env variables.

Clone the repo and run to install `wcgw_local` command

`pip install .`

Then run 

`wcgw_local  --limit 0.1` # Cost limit $0.1 

You can now directly write messages or press enter key to open vim for multiline message and text pasting.
