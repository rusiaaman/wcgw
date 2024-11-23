import re
from typing import Literal, Optional, Sequence
from pydantic import BaseModel


class BashCommand(BaseModel):
    command: str


Specials = Literal[
    "Key-up", "Key-down", "Key-left", "Key-right", "Enter", "Ctrl-c", "Ctrl-d", "Ctrl-z"
]


class BashInteraction(BaseModel):
    type: Literal["BashInteraction"]
    send_text: Optional[str] = None
    send_specials: Optional[Sequence[Specials]] = None
    send_ascii: Optional[Sequence[int]] = None


class ReadImage(BaseModel):
    file_path: str
    type: Literal["ReadImage"]


class Writefile(BaseModel):
    file_path: str
    file_content: str


class CreateFileNew(BaseModel):
    file_path: str
    file_content: str


class ReadFile(BaseModel):
    file_path: str  # The path to the file to read
    type: Literal["ReadFile"]


class FileEditFindReplace(BaseModel):
    file_path: str
    find_lines: str
    replace_with_lines: str


class ResetShell(BaseModel):
    should_reset: Literal[True]


class FileEdit(BaseModel):
    file_path: str
    file_edit_using_search_replace_blocks: str


class Initialize(BaseModel):
    type: Literal["Initialize"]