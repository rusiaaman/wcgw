import base64
import fnmatch
import glob
import importlib.metadata
import json
import mimetypes
import os
import time
import traceback
import uuid
from dataclasses import dataclass
from os.path import expanduser
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import (
    Callable,
    Literal,
    Optional,
    ParamSpec,
    Type,
    TypeVar,
)

import rich
import tokenizers  # type: ignore
import typer
import websockets
from openai.types.chat import (
    ChatCompletionMessageParam,
)
from pydantic import BaseModel, TypeAdapter
from syntax_checker import check_syntax
from typer import Typer
from websockets.sync.client import connect as syncconnect

from wcgw.client.bash_state.bash_state import WAITING_INPUT_MESSAGE, get_status

from ..types_ import (
    BashCommand,
    BashInteraction,
    CodeWriterMode,
    Console,
    ContextSave,
    FileEdit,
    Initialize,
    Modes,
    ModesConfig,
    ReadFiles,
    ReadImage,
    ResetShell,
    WriteIfEmpty,
)
from .bash_state.bash_state import (
    BashState,
    execute_bash,
)
from .file_ops.search_replace import search_replace_edit
from .memory import load_memory, save_memory
from .modes import (
    ARCHITECT_PROMPT,
    WCGW_PROMPT,
    code_writer_prompt,
    modes_to_state,
)
from .repo_ops.repo_context import get_repo_context


@dataclass
class Context:
    bash_state: BashState
    console: Console


INITIALIZED = False


def initialize(
    context: Context,
    any_workspace_path: str,
    read_files_: list[str],
    task_id_to_resume: str,
    max_tokens: Optional[int],
    mode: ModesConfig,
) -> tuple[str, Context]:
    # Expand the workspace path
    any_workspace_path = expand_user(any_workspace_path)
    repo_context = ""

    memory = ""
    loaded_state = None
    if task_id_to_resume:
        try:
            project_root_path, task_mem, loaded_state = load_memory(
                task_id_to_resume,
                max_tokens,
                lambda x: default_enc.encode(x).ids,
                lambda x: default_enc.decode(x),
            )
            memory = "Following is the retrieved task:\n" + task_mem
            if os.path.exists(project_root_path):
                any_workspace_path = project_root_path

        except Exception:
            memory = f'Error: Unable to load task with ID "{task_id_to_resume}" '

    folder_to_start = None
    if any_workspace_path:
        if os.path.exists(any_workspace_path):
            if os.path.isfile(any_workspace_path):
                # Set any_workspace_path to the directory containing the file
                # Add the file to read_files_ only if empty to avoid duplicates
                if not read_files_:
                    read_files_ = [any_workspace_path]
                any_workspace_path = os.path.dirname(any_workspace_path)
            repo_context, folder_to_start = get_repo_context(any_workspace_path, 200)

            repo_context = f"---\n# Workspace structure\n{repo_context}\n---\n"

            # update modes if they're relative
            if isinstance(mode, CodeWriterMode):
                mode.update_relative_globs(any_workspace_path)
            else:
                assert isinstance(mode, str)
        else:
            if os.path.abspath(any_workspace_path):
                os.makedirs(any_workspace_path, exist_ok=True)
                repo_context = f"\nInfo: Workspace path {any_workspace_path} did not exist. I've created it for you.\n"
                folder_to_start = Path(any_workspace_path)
            else:
                repo_context = (
                    f"\nInfo: Workspace path {any_workspace_path} does not exist."
                )
    # Restore bash state if available
    if loaded_state is not None:
        try:
            parsed_state = BashState.parse_state(loaded_state)
            if mode == "wcgw":
                context.bash_state.load_state(
                    parsed_state[0],
                    parsed_state[1],
                    parsed_state[2],
                    parsed_state[3],
                    parsed_state[4] + list(context.bash_state.whitelist_for_overwrite),
                    str(folder_to_start) if folder_to_start else "",
                )
            else:
                state = modes_to_state(mode)
                context.bash_state.load_state(
                    state[0],
                    state[1],
                    state[2],
                    state[3],
                    parsed_state[4] + list(context.bash_state.whitelist_for_overwrite),
                    str(folder_to_start) if folder_to_start else "",
                )
        except ValueError:
            context.console.print(traceback.format_exc())
            context.console.print("Error: couldn't load bash state")
            pass
    else:
        state = modes_to_state(mode)
        context.bash_state.load_state(
            state[0],
            state[1],
            state[2],
            state[3],
            list(context.bash_state.whitelist_for_overwrite),
            str(folder_to_start) if folder_to_start else "",
        )
    del mode

    initial_files_context = ""
    if read_files_:
        if folder_to_start:
            read_files_ = [
                os.path.join(folder_to_start, f) if not os.path.isabs(f) else f
                for f in read_files_
            ]
        initial_files = read_files(read_files_, max_tokens, context)
        initial_files_context = f"---\n# Requested files\n{initial_files}\n---\n"

    uname_sysname = os.uname().sysname
    uname_machine = os.uname().machine

    mode_prompt = ""
    if context.bash_state.mode == Modes.code_writer:
        mode_prompt = code_writer_prompt(
            context.bash_state.file_edit_mode.allowed_globs,
            context.bash_state.write_if_empty_mode.allowed_globs,
            "all" if context.bash_state.bash_command_mode.allowed_commands else [],
        )
    elif context.bash_state.mode == Modes.architect:
        mode_prompt = ARCHITECT_PROMPT
    else:
        mode_prompt = WCGW_PROMPT

    output = f"""
{mode_prompt}

# Environment
System: {uname_sysname}
Machine: {uname_machine}
Initialized in directory (also cwd): {context.bash_state.cwd}

{repo_context}

{initial_files_context}

---

{memory}
"""

    global INITIALIZED
    INITIALIZED = True

    return output, context


def reset_shell(context: Context) -> str:
    context.bash_state.reset_shell()
    return "Reset successful" + get_status(context.bash_state)


T = TypeVar("T")


def save_out_of_context(content: str, suffix: str) -> str:
    file_path = NamedTemporaryFile(delete=False, suffix=suffix).name
    with open(file_path, "w") as f:
        f.write(content)
    return file_path


def expand_user(path: str) -> str:
    if not path or not path.startswith("~"):
        return path
    return expanduser(path)


MEDIA_TYPES = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]


class ImageData(BaseModel):
    media_type: MEDIA_TYPES
    data: str

    @property
    def dataurl(self) -> str:
        return f"data:{self.media_type};base64," + self.data


Param = ParamSpec("Param")


def ensure_no_previous_output(
    context: Context,
) -> Callable[[Callable[Param, T]], Callable[Param, T]]:
    def decorator(func: Callable[Param, T]) -> Callable[Param, T]:
        def wrapper(*args: Param.args, **kwargs: Param.kwargs) -> T:
            if context.bash_state.state == "pending":
                raise ValueError(WAITING_INPUT_MESSAGE)

            return func(*args, **kwargs)

        return wrapper

    return decorator


def truncate_if_over(content: str, max_tokens: Optional[int]) -> str:
    if max_tokens and max_tokens > 0:
        tokens = default_enc.encode(content)
        n_tokens = len(tokens)
        if n_tokens > max_tokens:
            content = (
                default_enc.decode(tokens.ids[: max(0, max_tokens - 100)])
                + "\n(...truncated)"
            )

    return content


def read_image_from_shell(file_path: str, context: Context) -> ImageData:
    # Expand the path
    file_path = expand_user(file_path)

    if not os.path.isabs(file_path):
        file_path = os.path.join(context.bash_state.cwd, file_path)

    if not os.path.exists(file_path):
        raise ValueError(f"File {file_path} does not exist")

    with open(file_path, "rb") as image_file:
        image_bytes = image_file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_type = mimetypes.guess_type(file_path)[0]
        return ImageData(media_type=image_type, data=image_b64)  # type: ignore


def get_context_for_errors(
    errors: list[tuple[int, int]], file_content: str, max_tokens: Optional[int]
) -> str:
    file_lines = file_content.split("\n")
    min_line_num = max(0, min([error[0] for error in errors]) - 10)
    max_line_num = min(len(file_lines), max([error[0] for error in errors]) + 10)
    context_lines = file_lines[min_line_num:max_line_num]
    context = "\n".join(context_lines)

    if max_tokens is not None and max_tokens > 0:
        ntokens = len(default_enc.encode(context))
        if ntokens > max_tokens:
            return "Please re-read the file to understand the context"
    return f"Here's relevant snippet from the file where the syntax errors occured:\n```\n{context}\n```"


def write_file(
    writefile: WriteIfEmpty,
    error_on_exist: bool,
    max_tokens: Optional[int],
    context: Context,
) -> str:
    if not os.path.isabs(writefile.file_path):
        return f"Failure: file_path should be absolute path, current working directory is {context.bash_state.cwd}"
    else:
        path_ = expand_user(writefile.file_path)

    error_on_exist_ = (
        error_on_exist and path_ not in context.bash_state.whitelist_for_overwrite
    )

    # Validate using write_if_empty_mode after checking whitelist
    allowed_globs = context.bash_state.write_if_empty_mode.allowed_globs
    if allowed_globs != "all" and not any(
        fnmatch.fnmatch(path_, pattern) for pattern in allowed_globs
    ):
        return f"Error: updating file {path_} not allowed in current mode. Doesn't match allowed globs: {allowed_globs}"

    add_overwrite_warning = ""
    if (error_on_exist or error_on_exist_) and os.path.exists(path_):
        content = Path(path_).read_text().strip()
        if content:
            content = truncate_if_over(content, max_tokens)

            if error_on_exist_:
                return (
                    f"Error: can't write to existing file {path_}, use other functions to edit the file"
                    + f"\nHere's the existing content:\n```\n{content}\n```"
                )
            else:
                add_overwrite_warning = content

    # Since we've already errored once, add this to whitelist
    context.bash_state.add_to_whitelist_for_overwrite(path_)

    path = Path(path_)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with path.open("w") as f:
            f.write(writefile.file_content)
    except OSError as e:
        return f"Error: {e}"

    extension = Path(path_).suffix.lstrip(".")

    context.console.print(f"File written to {path_}")

    warnings = []
    try:
        check = check_syntax(extension, writefile.file_content)
        syntax_errors = check.description

        if syntax_errors:
            context_for_errors = get_context_for_errors(
                check.errors, writefile.file_content, max_tokens
            )
            context.console.print(f"W: Syntax errors encountered: {syntax_errors}")
            warnings.append(f"""
---
Warning: tree-sitter reported syntax errors
Syntax errors:
{syntax_errors}

{context_for_errors}
---
            """)

    except Exception:
        pass

    if add_overwrite_warning:
        warnings.append(
            "\n---\nWarning: a file already existed and it's now overwritten. Was it a mistake? If yes please revert your action."
            "\n---\n"
            + "Here's the previous content:\n```\n"
            + add_overwrite_warning
            + "\n```"
        )

    return "Success" + "".join(warnings)


def do_diff_edit(fedit: FileEdit, max_tokens: Optional[int], context: Context) -> str:
    try:
        return _do_diff_edit(fedit, max_tokens, context)
    except Exception as e:
        # Try replacing \"
        try:
            fedit = FileEdit(
                file_path=fedit.file_path,
                file_edit_using_search_replace_blocks=fedit.file_edit_using_search_replace_blocks.replace(
                    '\\"', '"'
                ),
            )
            return _do_diff_edit(fedit, max_tokens, context)
        except Exception:
            pass
        raise e


def _do_diff_edit(fedit: FileEdit, max_tokens: Optional[int], context: Context) -> str:
    context.console.log(f"Editing file: {fedit.file_path}")

    if not os.path.isabs(fedit.file_path):
        raise Exception(
            f"Failure: file_path should be absolute path, current working directory is {context.bash_state.cwd}"
        )
    else:
        path_ = expand_user(fedit.file_path)

    # Validate using file_edit_mode
    allowed_globs = context.bash_state.file_edit_mode.allowed_globs
    if allowed_globs != "all" and not any(
        fnmatch.fnmatch(path_, pattern) for pattern in allowed_globs
    ):
        raise Exception(
            f"Error: updating file {path_} not allowed in current mode. Doesn't match allowed globs: {allowed_globs}"
        )

    # The LLM is now aware that the file exists
    context.bash_state.add_to_whitelist_for_overwrite(path_)

    if not os.path.exists(path_):
        raise Exception(f"Error: file {path_} does not exist")

    with open(path_) as f:
        apply_diff_to = f.read()

    fedit.file_edit_using_search_replace_blocks = (
        fedit.file_edit_using_search_replace_blocks.strip()
    )
    lines = fedit.file_edit_using_search_replace_blocks.split("\n")

    apply_diff_to, comments = search_replace_edit(
        lines, apply_diff_to, context.console.log
    )

    with open(path_, "w") as f:
        f.write(apply_diff_to)

    syntax_errors = ""
    extension = Path(path_).suffix.lstrip(".")
    try:
        check = check_syntax(extension, apply_diff_to)
        syntax_errors = check.description
        if syntax_errors:
            context_for_errors = get_context_for_errors(
                check.errors, apply_diff_to, max_tokens
            )

            context.console.print(f"W: Syntax errors encountered: {syntax_errors}")
            return f"""{comments}
---
Tree-sitter reported syntax errors, please re-read the file and fix if there are any errors.
Syntax errors:
{syntax_errors}

{context_for_errors}
"""
    except Exception:
        pass

    return comments


TOOLS = (
    BashCommand
    | BashInteraction
    | ResetShell
    | WriteIfEmpty
    | FileEdit
    | ReadImage
    | ReadFiles
    | Initialize
    | ContextSave
)


def which_tool(args: str) -> TOOLS:
    adapter = TypeAdapter[TOOLS](TOOLS, config={"extra": "forbid"})
    return adapter.validate_python(json.loads(args))


def which_tool_name(name: str) -> Type[TOOLS]:
    if name == "BashCommand":
        return BashCommand
    elif name == "BashInteraction":
        return BashInteraction
    elif name == "ResetShell":
        return ResetShell
    elif name == "WriteIfEmpty":
        return WriteIfEmpty
    elif name == "FileEdit":
        return FileEdit
    elif name == "ReadImage":
        return ReadImage
    elif name == "ReadFiles":
        return ReadFiles
    elif name == "Initialize":
        return Initialize
    elif name == "ContextSave":
        return ContextSave
    else:
        raise ValueError(f"Unknown tool name: {name}")


TOOL_CALLS: list[TOOLS] = []


def get_tool_output(
    context: Context,
    args: dict[object, object] | TOOLS,
    enc: tokenizers.Tokenizer,
    limit: float,
    loop_call: Callable[[str, float], tuple[str, float]],
    max_tokens: Optional[int],
) -> tuple[list[str | ImageData], float]:
    global TOOL_CALLS, INITIALIZED
    if isinstance(args, dict):
        adapter = TypeAdapter[TOOLS](TOOLS, config={"extra": "forbid"})
        arg = adapter.validate_python(args)
    else:
        arg = args
    output: tuple[str | ImageData, float]
    TOOL_CALLS.append(arg)

    if isinstance(arg, (BashCommand | BashInteraction)):
        context.console.print("Calling execute bash tool")
        if not INITIALIZED:
            raise Exception("Initialize tool not called yet.")

        output = execute_bash(
            context.bash_state, enc, arg, max_tokens, arg.wait_for_seconds
        )
    elif isinstance(arg, WriteIfEmpty):
        context.console.print("Calling write file tool")
        if not INITIALIZED:
            raise Exception("Initialize tool not called yet.")

        output = write_file(arg, True, max_tokens, context), 0
    elif isinstance(arg, FileEdit):
        context.console.print("Calling full file edit tool")
        if not INITIALIZED:
            raise Exception("Initialize tool not called yet.")

        output = do_diff_edit(arg, max_tokens, context), 0.0
    elif isinstance(arg, ReadImage):
        context.console.print("Calling read image tool")
        output = read_image_from_shell(arg.file_path, context), 0.0
    elif isinstance(arg, ReadFiles):
        context.console.print("Calling read file tool")
        output = read_files(arg.file_paths, max_tokens, context), 0.0
    elif isinstance(arg, ResetShell):
        context.console.print("Calling reset shell tool")
        output = reset_shell(context), 0.0
    elif isinstance(arg, Initialize):
        context.console.print("Calling initial info tool")
        output_, context = initialize(
            context,
            arg.any_workspace_path,
            arg.initial_files_to_read,
            arg.task_id_to_resume,
            max_tokens,
            arg.mode,
        )
        output = output_, 0.0
    elif isinstance(arg, ContextSave):
        context.console.print("Calling task memory tool")
        relevant_files = []
        warnings = ""
        for fglob in arg.relevant_file_globs:
            fglob = expand_user(fglob)
            if not os.path.isabs(fglob) and arg.project_root_path:
                fglob = os.path.join(arg.project_root_path, fglob)
            globs = glob.glob(fglob, recursive=True)
            relevant_files.extend(globs[:1000])
            if not globs:
                warnings += f"Warning: No files found for the glob: {fglob}\n"
        relevant_files_data = read_files(relevant_files[:10_000], None, context)
        output_ = save_memory(arg, relevant_files_data, context.bash_state.serialize())
        if not relevant_files and arg.relevant_file_globs:
            output_ = f'Error: No files found for the given globs. Context file successfully saved at "{output_}", but please fix the error.'
        elif warnings:
            output_ = warnings + "\nContext file successfully saved at " + output_
        output = output_, 0.0
    else:
        raise ValueError(f"Unknown tool: {arg}")
    if isinstance(output[0], str):
        context.console.print(str(output[0]))
    else:
        context.console.print(f"Received {type(output[0])} from tool")
    return [output[0]], output[1]


History = list[ChatCompletionMessageParam]

default_enc: tokenizers.Tokenizer = tokenizers.Tokenizer.from_pretrained(
    "Xenova/claude-tokenizer"
)
curr_cost = 0.0


class Mdata(BaseModel):
    data: (
        BashCommand
        | BashInteraction
        | WriteIfEmpty
        | ResetShell
        | FileEdit
        | str
        | ReadFiles
        | Initialize
        | ContextSave
    )


def register_client(server_url: str, client_uuid: str = "") -> None:
    global default_enc, curr_cost
    # Generate a unique UUID for this client
    if not client_uuid:
        client_uuid = str(uuid.uuid4())

    # Create the WebSocket connection and context
    the_console = rich.console.Console(style="magenta", highlight=False, markup=False)
    bash_state = BashState(the_console, os.getcwd(), None, None, None, None)
    context = Context(bash_state=bash_state, console=the_console)

    try:
        with syncconnect(f"{server_url}/{client_uuid}") as websocket:
            server_version = str(websocket.recv())
            print(f"Server version: {server_version}")
            client_version = importlib.metadata.version("wcgw")
            websocket.send(client_version)

            print(f"Connected. Share this user id with the chatbot: {client_uuid}")
            while True:
                # Wait to receive data from the server
                message = websocket.recv()
                mdata = Mdata.model_validate_json(message)
                if isinstance(mdata.data, str):
                    raise Exception(mdata)
                try:
                    outputs, cost = get_tool_output(
                        context,
                        mdata.data,
                        default_enc,
                        0.0,
                        lambda x, y: ("", 0),
                        8000,
                    )
                    output = outputs[0]
                    curr_cost += cost
                    print(f"{curr_cost=}")
                except Exception as e:
                    output = f"GOT EXCEPTION while calling tool. Error: {e}"
                    context.console.print(traceback.format_exc())
                assert isinstance(output, str)
                websocket.send(output)

    except (websockets.ConnectionClosed, ConnectionError, OSError):
        print(f"Connection closed for UUID: {client_uuid}, retrying")
        time.sleep(0.5)
        register_client(server_url, client_uuid)


run = Typer(pretty_exceptions_show_locals=False, no_args_is_help=True)


@run.command()
def app(
    server_url: str = "",
    client_uuid: Optional[str] = None,
    version: bool = typer.Option(False, "--version", "-v"),
) -> None:
    if version:
        version_ = importlib.metadata.version("wcgw")
        print(f"wcgw version: {version_}")
        exit()
    if not server_url:
        server_url = os.environ.get("WCGW_RELAY_SERVER", "")
        if not server_url:
            print(
                "Error: Please provide relay server url using --server_url or WCGW_RELAY_SERVER environment variable"
            )
            print(
                "\tNOTE: you need to run a relay server first, author doesn't host a relay server anymore."
            )
            print("\thttps://github.com/rusiaaman/wcgw/blob/main/openai.md")
            print("\tExample `--server-url=ws://localhost:8000/v1/register`")
            raise typer.Exit(1)
    register_client(server_url, client_uuid or "")


def read_files(
    file_paths: list[str], max_tokens: Optional[int], context: Context
) -> str:
    message = ""
    for i, file in enumerate(file_paths):
        try:
            content, truncated, tokens = read_file(file, max_tokens, context)
        except Exception as e:
            message += f"\n{file}: {str(e)}\n"
            continue

        if max_tokens:
            max_tokens = max_tokens - tokens

        message += f"\n``` {file}\n{content}\n"

        if truncated or (max_tokens and max_tokens <= 0):
            not_reading = file_paths[i + 1 :]
            if not_reading:
                message += f"\nNot reading the rest of the files: {', '.join(not_reading)} due to token limit, please call again"
            break
        else:
            message += "```"

    return message


def read_file(
    file_path: str, max_tokens: Optional[int], context: Context
) -> tuple[str, bool, int]:
    context.console.print(f"Reading file: {file_path}")

    # Expand the path before checking if it's absolute
    file_path = expand_user(file_path)

    if not os.path.isabs(file_path):
        raise ValueError(
            f"Failure: file_path should be absolute path, current working directory is {context.bash_state.cwd}"
        )

    context.bash_state.add_to_whitelist_for_overwrite(file_path)

    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"Error: file {file_path} does not exist")

    with path.open("r") as f:
        content = f.read(10_000_000)

    truncated = False
    tokens_counts = 0
    if max_tokens is not None:
        tokens = default_enc.encode(content)
        tokens_counts = len(tokens)
        if len(tokens) > max_tokens:
            content = default_enc.decode(tokens.ids[:max_tokens])
            rest = save_out_of_context(
                default_enc.decode(tokens.ids[max_tokens:]), Path(file_path).suffix
            )
            content += f"\n(...truncated)\n---\nI've saved the continuation in a new file. Please read: `{rest}`"
            truncated = True
    return content, truncated, tokens_counts
