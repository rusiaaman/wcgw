import os
from enum import Enum
from typing import Any, Literal, Optional, Sequence, Union

from pydantic import BaseModel as PydanticBaseModel


class NoExtraArgs(PydanticBaseModel):
    class Config:
        extra = "forbid"


BaseModel = NoExtraArgs


class Modes(str, Enum):
    wcgw = "wcgw"
    architect = "architect"
    code_writer = "code_writer"


class CodeWriterMode(BaseModel):
    allowed_globs: Literal["all"] | list[str]
    allowed_commands: Literal["all"] | list[str]

    def update_relative_globs(self, workspace_root: str) -> None:
        """Update globs if they're relative paths"""
        if self.allowed_globs != "all":
            self.allowed_globs = [
                glob if os.path.isabs(glob) else os.path.join(workspace_root, glob)
                for glob in self.allowed_globs
            ]


ModesConfig = Union[Literal["wcgw", "architect"], CodeWriterMode]


class Initialize(BaseModel):
    any_workspace_path: str
    initial_files_to_read: list[str]
    task_id_to_resume: str
    mode_name: Literal["wcgw", "architect", "code_writer"]
    code_writer_config: Optional[CodeWriterMode] = None

    def model_post_init(self, __context: Any) -> None:
        if self.mode_name == "code_writer":
            assert (
                self.code_writer_config is not None
            ), "code_writer_config can't be null when the mode is code_writer"
        return super().model_post_init(__context)

    @property
    def mode(self) -> ModesConfig:
        if self.mode_name == "wcgw":
            return "wcgw"
        if self.mode_name == "architect":
            return "architect"
        assert (
            self.code_writer_config is not None
        ), "code_writer_config can't be null when the mode is code_writer"
        return self.code_writer_config


class BashCommand(BaseModel):
    command: str
    wait_for_seconds: Optional[int] = None


Specials = Literal[
    "Key-up", "Key-down", "Key-left", "Key-right", "Enter", "Ctrl-c", "Ctrl-d", "Ctrl-z"
]


class BashInteraction(BaseModel):
    send_text: Optional[str] = None
    send_specials: Optional[Sequence[Specials]] = None
    send_ascii: Optional[Sequence[int]] = None
    wait_for_seconds: Optional[int] = None


class ReadImage(BaseModel):
    file_path: str


class WriteIfEmpty(BaseModel):
    file_path: str
    file_content: str


class ReadFiles(BaseModel):
    file_paths: list[str]


class FileEditFindReplace(BaseModel):
    file_path: str
    find_lines: str
    replace_with_lines: str


class ResetShell(BaseModel):
    should_reset: Literal[True]


class FileEdit(BaseModel):
    file_path: str
    file_edit_using_search_replace_blocks: str


class GetScreenInfo(BaseModel):
    docker_image_id: str


class ScreenShot(BaseModel):
    take_after_delay_seconds: int


class MouseMove(BaseModel):
    x: int
    y: int
    do_left_click_on_move: bool


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


class ContextSave(BaseModel):
    id: str
    project_root_path: str
    description: str
    relevant_file_globs: list[str]
