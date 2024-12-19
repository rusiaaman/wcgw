import re
from typing import Literal, Optional, Sequence
from pydantic import BaseModel


class BashCommand(BaseModel):
    command: str
    wait_for_seconds: Optional[int] = None


Specials = Literal[
    "Key-up", "Key-down", "Key-left", "Key-right", "Enter", "Ctrl-c", "Ctrl-d", "Ctrl-z"
]


class BashInteraction(BaseModel):
    type: Literal["BashInteraction"]
    send_text: Optional[str] = None
    send_specials: Optional[Sequence[Specials]] = None
    send_ascii: Optional[Sequence[int]] = None
    wait_for_seconds: Optional[int] = None


class ReadImage(BaseModel):
    file_path: str
    type: Literal["ReadImage"]


class WriteIfEmpty(BaseModel):
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


class GetScreenInfo(BaseModel):
    type: Literal["GetScreenInfo"]
    docker_image_id: str


class ScreenShot(BaseModel):
    type: Literal["ScreenShot"]
    take_after_delay_seconds: int


class MouseMove(BaseModel):
    x: int
    y: int
    do_left_click_on_move: bool
    type: Literal["MouseMove"]


class LeftClickDrag(BaseModel):
    x: int
    y: int


class MouseButton(BaseModel):
    button_type: Literal[
        "left_click",
        "right_click",
        "middle_click",
        "double_click",
        "scroll_up",
        "scroll_down",
    ]


class Mouse(BaseModel):
    action: MouseButton | LeftClickDrag | MouseMove


class Keyboard(BaseModel):
    action: Literal["key", "type"]
    text: str
