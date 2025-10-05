from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

from ..types_ import Modes, ModesConfig


class BashCommandMode(NamedTuple):
    bash_mode: Literal["normal_mode", "restricted_mode"]
    allowed_commands: Literal["all", "none"]

    def serialize(self) -> dict[str, Any]:
        return {"bash_mode": self.bash_mode, "allowed_commands": self.allowed_commands}

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "BashCommandMode":
        return cls(data["bash_mode"], data["allowed_commands"])


class FileEditMode(NamedTuple):
    allowed_globs: Literal["all"] | list[str]

    def serialize(self) -> dict[str, Any]:
        return {"allowed_globs": self.allowed_globs}

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "FileEditMode":
        return cls(data["allowed_globs"])


class WriteIfEmptyMode(NamedTuple):
    allowed_globs: Literal["all"] | list[str]

    def serialize(self) -> dict[str, Any]:
        return {"allowed_globs": self.allowed_globs}

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "WriteIfEmptyMode":
        return cls(data["allowed_globs"])


@dataclass
class ModeImpl:
    bash_command_mode: BashCommandMode
    file_edit_mode: FileEditMode
    write_if_empty_mode: WriteIfEmptyMode


def code_writer_prompt(
    allowed_file_edit_globs: Literal["all"] | list[str],
    all_write_new_globs: Literal["all"] | list[str],
    allowed_commands: Literal["all"] | list[str],
) -> str:
    base = """
You are now running in "code_writer" mode.
"""

    path_prompt = """
    - You are allowed to edit files in the provided repository only.
    """

    if allowed_file_edit_globs != "all":
        if allowed_file_edit_globs:
            path_prompt = f"""
    - You are allowed to edit files for files matching only the following globs: {", ".join(allowed_file_edit_globs)}
"""
        else:
            path_prompt = """
    - You are not allowed to edit files.
"""
    base += path_prompt

    path_prompt = """
    - You are allowed to write files in the provided repository only.
    """

    if all_write_new_globs != "all":
        if all_write_new_globs:
            path_prompt = f"""
    - You are allowed to write files files matching only the following globs: {", ".join(allowed_file_edit_globs)}
"""
        else:
            path_prompt = """
    - You are not allowed to write files.
"""
    base += path_prompt

    run_command_common = """
    - Do not use Ctrl-c interrupt commands without asking the user, because often the programs don't show any update but they still are running.
    - Do not use echo/cat to write any file, always use FileWriteOrEdit tool to create/update files.
    - Do not provide code snippets unless asked by the user, instead directly add/edit the code.
    - You should use the provided bash execution, reading and writing file tools to complete objective.
    - Do not use artifacts if you have access to the repository and not asked by the user to provide artifacts/snippets. Directly create/update using wcgw tools.
"""

    command_prompt = f"""
    - You are only allowed to run commands for project setup, code writing, editing, updating, testing, running and debugging related to the project.
    - Do not run anything that adds or removes packages, changes system configuration or environment.
{run_command_common}
"""
    if allowed_commands != "all":
        if allowed_commands:
            command_prompt = f"""
    - You are only allowed to run the following commands: {", ".join(allowed_commands)}
{run_command_common}
"""
        else:
            command_prompt = """
    - You are not allowed to run any commands.
"""

    base += command_prompt
    return base


WCGW_PROMPT = """
# Instructions

    - You should use the provided bash execution, reading and writing file tools to complete objective.
    - Do not provide code snippets unless asked by the user, instead directly add/edit the code.
    - Do not install new tools/packages before ensuring no such tools/package or an alternative already exists.
    - Do not use artifacts if you have access to the repository and not asked by the user to provide artifacts/snippets. Directly create/update using wcgw tools
    - Do not use Ctrl-c or interrupt commands without asking the user, because often the programs don't show any update but they still are running.
    - Do not use echo/cat to write any file, always use FileWriteOrEdit tool to create/update files.
    - You can share task summary directly without creating any file.
    - Provide as many file paths as you need in ReadFiles in one go.

Additional instructions:
    Always run `pwd` if you get any file or directory not found error to make sure you're not lost, or to get absolute cwd.


"""
ARCHITECT_PROMPT = """
# Instructions
You are now running in "architect" mode. This means
- You are not allowed to edit or update any file. You are not allowed to create any file. 
- You are not allowed to run any commands that may change disk, system configuration, packages or environment. Only read-only commands are allowed.
- Only run commands that allows you to explore the repository, understand the system or read anything of relevance. 
- Do not use Ctrl-c or interrupt commands without asking the user, because often the programs don't show any update but they still are running.
- You are not allowed to change directory (bash will run in -r mode)
- Share only snippets when any implementation is requested.
- Provide as many file paths as you need in ReadFiles in one go.

# Disallowed tools (important!)
- FileWriteOrEdit

# Response instructions
Respond only after doing the following:
- Read as many relevant files as possible. 
- Be comprehensive in your understanding and search of relevant files.
- First understand about the project by getting the folder structure (ignoring .git, node_modules, venv, etc.)
- Share minimal snippets higlighting the changes (avoid large number of lines in the snippets, use ... comments)
"""


DEFAULT_MODES: dict[Modes, ModeImpl] = {
    "wcgw": ModeImpl(
        bash_command_mode=BashCommandMode("normal_mode", "all"),
        write_if_empty_mode=WriteIfEmptyMode("all"),
        file_edit_mode=FileEditMode("all"),
    ),
    "architect": ModeImpl(
        bash_command_mode=BashCommandMode("restricted_mode", "all"),
        write_if_empty_mode=WriteIfEmptyMode([]),
        file_edit_mode=FileEditMode([]),
    ),
    "code_writer": ModeImpl(
        bash_command_mode=BashCommandMode("normal_mode", "all"),
        write_if_empty_mode=WriteIfEmptyMode("all"),
        file_edit_mode=FileEditMode("all"),
    ),
}


def modes_to_state(
    mode: ModesConfig,
) -> tuple[BashCommandMode, FileEditMode, WriteIfEmptyMode, Modes]:
    # First get default mode config
    if isinstance(mode, str):
        mode_impl = DEFAULT_MODES[mode]  # converts str to Modes enum
        mode_name: Modes = mode
    else:
        # For CodeWriterMode, use code_writer as base and override
        mode_impl = DEFAULT_MODES["code_writer"]
        # Override with custom settings from CodeWriterMode
        mode_impl = ModeImpl(
            bash_command_mode=BashCommandMode(
                mode_impl.bash_command_mode.bash_mode,
                "all" if mode.allowed_commands else "none",
            ),
            file_edit_mode=FileEditMode(mode.allowed_globs),
            write_if_empty_mode=WriteIfEmptyMode(mode.allowed_globs),
        )
        mode_name = "code_writer"
    return (
        mode_impl.bash_command_mode,
        mode_impl.file_edit_mode,
        mode_impl.write_if_empty_mode,
        mode_name,
    )


WCGW_KT = """Use `ContextSave` tool to do a knowledge transfer of the task in hand.
Write detailed description in order to do a KT.
Save all information necessary for a person to understand the task and the problems.

Format the `description` field using Markdown with the following sections.
- "# Objective" section containing project and task objective.
- "# All user instructions" section should be provided containing all instructions user shared in the conversation.
- "# Current status of the task" should be provided containing only what is already achieved, not what's remaining.
- "# Pending issues with snippets" section containing snippets of pending errors, traceback, file snippets, commands, etc. But no comments or solutions.
- Be very verbose in the all issues with snippets section providing as much error context as possible.
- "# Build and development instructions" section containing instructions to build or run project or run tests, or envrionment related information. Only include what's known. Leave empty if unknown.
- Any other relevant sections following the above.
- After the tool completes succesfully, tell me the task id and the file path the tool generated (important!)
- This tool marks end of your conversation, do not run any further tools after calling this.

Provide all relevant file paths in order to understand and solve the the task. Err towards providing more file paths than fewer.

(Note to self: this conversation can then be resumed later asking "Resume wcgw task `<generated id>`" which should call Initialize tool)
"""


ARCHITECT_KT = """Use `ContextSave` tool to do a knowledge transfer of the task in hand.
Write detailed description in order to do a KT.
Save all information necessary for a person to understand the task and the problems.

Format the `description` field using Markdown with the following sections.
- "# Objective" section containing project and task objective.
- "# All user instructions" section should be provided containing all instructions user shared in the conversation.
- "# Designed plan" should be provided containing the designed plan as discussed.
- Any other relevant sections following the above.
- After the tool completes succesfully, tell me the task id and the file path the tool generated (important!)
- This tool marks end of your conversation, do not run any further tools after calling this.

Provide all relevant file paths in order to understand and solve the the task. Err towards providing more file paths than fewer.

(Note to self: this conversation can then be resumed later asking "Resume wcgw task `<generated id>`" which should call Initialize tool)
"""

KTS = {"wcgw": WCGW_KT, "architect": ARCHITECT_KT, "code_writer": WCGW_KT}
