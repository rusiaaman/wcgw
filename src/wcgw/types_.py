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
    type: Literal["ReadImage"] = "ReadImage"


class Writefile(BaseModel):
    file_path: str
    file_content: str


class CreateFileNew(BaseModel):
    file_path: str
    file_content: str


class FileEditFindReplace(BaseModel):
    file_path: str
    find_lines: str
    replace_with_lines: str


class ResetShell(BaseModel):
    should_reset: Literal[True] = True


class FullFileEdit(BaseModel):
    file_path: str
    file_edit_using_searh_replace_blocks: str
