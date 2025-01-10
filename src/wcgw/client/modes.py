from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

from ..types_ import Modes


@dataclass
class RestrictedGlobs:
    allowed_globs: list[str]


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
    allowed_globs: Literal["all"] | list[str],
    allowed_commands: Literal["all"] | list[str],
) -> str:
    base = """You have to run in "code_writer" mode. This means
"""

    path_prompt = """
    - You are allowed to create and update files in the provided repository only.
    """

    if allowed_globs != "all" and allowed_globs:
        path_prompt = f"""
- You are allowed to create and update files in the following globs: {', '.join(allowed_globs)}
"""
    base += path_prompt

    command_prompt = """
- You are only allowed to run commands for project setup, code writing, testing, running and debugging related to the proejct.
- Do not run anything that adds or removes packages, changes system configuration or environment.
"""
    if allowed_commands != "all":
        command_prompt = f"""
- You are only allowed to run the following commands: {', '.join(allowed_commands)}
"""

    base += command_prompt
    return base


ARCHITECT_PROMPT = """You have to run in "architect" mode. This means
- You are not allowed to edit or update any file. You are not allowed to create any file. 
- You are not allowed to run any commands that may change disk, system configuration, packages or environment. Only read-only commands are allowed.
- Only run commands that allows you to explore the repository, understand the system or read anything of relevance. 

Your response should be in self-critique and brainstorm style.
- Read as many relevant files as possible. 
- Be comprehensive in your understanding and search of relevant files.
"""
DEFAULT_MODES: dict[Modes, ModeImpl] = {
    Modes.wcgw: ModeImpl(
        bash_command_mode=BashCommandMode("normal_mode", "all"),
        write_if_empty_mode=WriteIfEmptyMode("all"),
        file_edit_mode=FileEditMode("all"),
    ),
    Modes.architect: ModeImpl(
        bash_command_mode=BashCommandMode("restricted_mode", "all"),
        write_if_empty_mode=WriteIfEmptyMode([]),
        file_edit_mode=FileEditMode([]),
    ),
    Modes.code_writer: ModeImpl(
        bash_command_mode=BashCommandMode("restricted_mode", "all"),
        write_if_empty_mode=WriteIfEmptyMode("all"),
        file_edit_mode=FileEditMode("all"),
    ),
}
