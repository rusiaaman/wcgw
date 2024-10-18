# Shell access to chatgpt.com

### 🚀 Highlights
- ⚡ **Full Shell Access**: No restrictions, complete control.
- ⚡ **Create, Execute, Iterate**: Seamless workflow for development and execution.
- ⚡ **Interactive Command Handling**: Supports interactive commands with ease.


###  🪜 Steps: 
1. Run the [cli client](https://github.com/rusiaaman/wcgw?tab=readme-ov-file#client) in any directory of choice.
2. Share the generated id with the GPT: `https://chatgpt.com/g/g-Us0AAXkRh-wcgw-giving-shell-access`
3. The custom GPT can now run any command on your cli

## Client

### Option 1: using pip
```sh
$ pip install wcgw
$ wcgw
```

### Option 2: using uv
```sh
$ curl -LsSf https://astral.sh/uv/install.sh | sh
$ uv tool run --python 3.12 wcgw
```

This will print a UUID that you need to share with the gpt.


## Chat
https://chatgpt.com/g/g-Us0AAXkRh-wcgw-giving-shell-access

Add user id the client generated to the first message along with the instructions.

# How it works
Your commands are relayed through a server I've hosted at https://wcgw.arcfu.com. The code for that is at `src/relay/serve.py`. 

The user id that you share with chatgpt is added in the request it sents to the relay server which holds a websocket with the terminal client.
