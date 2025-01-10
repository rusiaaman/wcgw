from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

from ..types_ import Modes, ModesConfig


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
    allowed_file_edit_globs: Literal["all"] | list[str],
    all_write_new_globs: Literal["all"] | list[str],
    allowed_commands: Literal["all"] | list[str],
) -> str:
    base = """You have to run in "code_writer" mode. This means
"""

    path_prompt = """
    - You are allowed to edit or update files in the provided repository only.
    """

    if allowed_file_edit_globs != "all" and allowed_file_edit_globs:
        path_prompt = f"""
- You are allowed to edit and update files only in the following globs: {', '.join(allowed_file_edit_globs)}
"""
    base += path_prompt

    path_prompt = """
    - You are allowed to create new files in the provided repository only.
    """

    if all_write_new_globs != "all" and all_write_new_globs:
        path_prompt = f"""
- You are allowed to create new files only in the following globs: {', '.join(allowed_file_edit_globs)}
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


def modes_to_state(
    mode: ModesConfig,
) -> tuple[BashCommandMode, FileEditMode, WriteIfEmptyMode, Modes]:
    # First get default mode config
    if isinstance(mode, str):
        mode_impl = DEFAULT_MODES[Modes[mode]]  # converts str to Modes enum
        mode_name = Modes[mode]
    else:
        # For CodeWriterMode, use code_writer as base and override
        mode_impl = DEFAULT_MODES[Modes.code_writer]
        # Override with custom settings from CodeWriterMode
        mode_impl = ModeImpl(
            bash_command_mode=BashCommandMode(
                mode_impl.bash_command_mode.bash_mode,
                "all" if mode.allowed_commands == "all" else "none",
            ),
            file_edit_mode=FileEditMode(mode.allowed_globs),
            write_if_empty_mode=WriteIfEmptyMode(mode.allowed_globs),
        )
        mode_name = Modes.code_writer
    return (
        mode_impl.bash_command_mode,
        mode_impl.file_edit_mode,
        mode_impl.write_if_empty_mode,
        mode_name,
    )
