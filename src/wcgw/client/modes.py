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
    def deserialize(cls, data: dict[str, Any])-> "BashCommandMode":
        return cls(data["bash_mode"], data["allowed_commands"])


class FileEditMode(NamedTuple):
    allowed_globs: Literal["all"] | list[str]

    def serialize(self) -> dict[str, Any]:
        return {"allowed_globs": self.allowed_globs}

    @classmethod
    def deserialize(cls, data: dict[str, Any])-> "FileEditMode":
        return cls(data["allowed_globs"])


class WriteIfEmptyMode(NamedTuple):
    allowed_globs: Literal["all"] | list[str]

    def serialize(self) -> dict[str, Any]:
        return {"allowed_globs": self.allowed_globs}

    @classmethod
    def deserialize(cls, data: dict[str, Any])-> "WriteIfEmptyMode":
        return cls(data["allowed_globs"])


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
