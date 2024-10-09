# Giving full shell access to Chatgpt web (What could go wrong?)
Steps: 
1. First run the client in any directory of choice
2. Use this custom gpt `https://chatgpt.com/g/g-Us0AAXkRh-wcgw-giving-shell-access` to let it interact with your shell.

## Client

### Option 1: using pip
```sh
$ pip install wcgw
$ wcgw
```

### Option 2: using uv
```sh
$ curl -LsSf https://astral.sh/uv/install.sh | sh
$ uv tool run wcgw
```

This will print a UUID that you need to share with the gpt.


## Chat
https://chatgpt.com/g/g-Us0AAXkRh-wcgw-giving-shell-access

Add user id the client generated to the first message along with the instructions.

# How does it work?
Your commands are relayed through a server I've hosted at https://wcgw.arcfu.com. The code for that is at `src/relay/serve.py`. 

The user id that you share with chatgpt is added in the request it sents to the relay server which holds a websocket with the terminal client.
