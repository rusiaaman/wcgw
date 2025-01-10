from dataclasses import dataclass
from typing import Literal, NamedTuple

from ..types_ import Modes


@dataclass
class RestrictedGlobs:
    allowed_globs: list[str]


class BashCommandMode(NamedTuple):
    bash_mode: Literal[
        "normal_mode", "restricted_mode"
    ]  # restricted_mode runs 'bash --restricted'
    allowed_commands: Literal["all", "none"]  # Allows all or none


class FileEditMode(NamedTuple):
    allowed_globs: (
        Literal["all"] | list[str]
    )  # Allows all or a set of globs. Leave it empty to disable FileEdit.


class WriteIfEmptyMode(NamedTuple):
    allowed_globs: (
        Literal["all"] | list[str]
    )  # Allows all or a set of globs. Leave it empty to disable WriteIfEmpty.


@dataclass
class ModeImpl:
    prompt: str
    bash_command_mode: BashCommandMode
    file_edit_mode: FileEditMode
    write_if_empty_mode: WriteIfEmptyMode


DEFAULT_MODES: dict[Modes, ModeImpl] = {
    Modes.wcgw: ModeImpl(
        prompt="",
        bash_command_mode=BashCommandMode("normal_mode", "all"),
        write_if_empty_mode=WriteIfEmptyMode("all"),
        file_edit_mode=FileEditMode("all"),
    ),
    Modes.architect: ModeImpl(
        prompt="",
        bash_command_mode=BashCommandMode("restricted_mode", "all"),
        write_if_empty_mode=WriteIfEmptyMode([]),
        file_edit_mode=FileEditMode([]),
    ),
    Modes.code_writer: ModeImpl(
        prompt="",
        bash_command_mode=BashCommandMode("restricted_mode", "all"),
        write_if_empty_mode=WriteIfEmptyMode("all"),
        file_edit_mode=FileEditMode("all"),
    ),
}
