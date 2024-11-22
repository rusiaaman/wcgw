import re
from typing import Literal, Optional, Sequence
from pydantic import BaseModel


class BashCommand(BaseModel):
    command: str


Specials = Literal[
    "Key-up", "Key-down", "Key-left", "Key-right", "Enter", "Ctrl-c", "Ctrl-d", "Ctrl-z"
]


class BashInteraction(BaseModel):
    send_text: Optional[str] = None
    send_specials: Optional[Sequence[Specials]] = None
    send_ascii: Optional[Sequence[int]] = None

    def model_post_init(self, __context: object) -> None:
        # Ensure only one of the fields is set
        if (
            sum(
                [
                    int(bool(self.send_text)),
                    int(bool(self.send_specials)),
                    int(bool(self.send_ascii)),
                ]
            )
            != 1
        ):
            raise ValueError(
                "Exactly one of 'send_text', 'send_specials', or 'send_ascii' must be set"
            )


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
    should_reset: Literal[True] = True


class FileEdit(BaseModel):
    file_path: str
    file_edit_using_search_replace_blocks: str

    def model_post_init(self, __context: object) -> None:
        # Ensure first line is "<<<<<<< SEARCH"

        if not re.match(r"^<<<<<<+\s*SEARCH\s*$", self.file_edit_using_search_replace_blocks.split("\n")[0]):

            raise ValueError("First line of file_edit_using_search_replace_blocks must be '<<<<<<< SEARCH'")
