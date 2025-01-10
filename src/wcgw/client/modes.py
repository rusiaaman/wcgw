from dataclasses import dataclass
from typing import Literal, Protocol

from ..types_ import Modes


@dataclass
class RestrictedCommands:
    allowed_commands: list[str]


@dataclass
class RestrictedGlobs:
    allowed_globs: list[str]


Skills = (
    Literal["file_edits", "write_new_files", "all_commands"]
    | RestrictedCommands
    | RestrictedGlobs
)


class ModeImpl(Protocol):
    prompt: str
    allowed_skills: set[Skills]


MODES_IMPL = dict[Modes, ModeImpl]()


# Add all modes' implementations here
