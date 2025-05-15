import os
from typing import Any, List, Literal, Optional, Protocol, Sequence, Union

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, PrivateAttr


class NoExtraArgs(PydanticBaseModel):
    class Config:
        extra = "forbid"


BaseModel = NoExtraArgs


Modes = Literal["wcgw", "architect", "code_writer"]


class CodeWriterMode(BaseModel):
    allowed_globs: Literal["all"] | list[str]
    allowed_commands: Literal["all"] | list[str]

    def model_post_init(self, _: Any) -> None:
        # Patch frequently wrong output trading off accuracy
        # in rare case there's a file named 'all' or a command named 'all'
        if len(self.allowed_commands) == 1:
            if self.allowed_commands[0] == "all":
                self.allowed_commands = "all"
        if len(self.allowed_globs) == 1:
            if self.allowed_globs[0] == "all":
                self.allowed_globs = "all"

    def update_relative_globs(self, workspace_root: str) -> None:
        """Update globs if they're relative paths"""
        if self.allowed_globs != "all":
            self.allowed_globs = [
                glob if os.path.isabs(glob) else os.path.join(workspace_root, glob)
                for glob in self.allowed_globs
            ]


ModesConfig = Union[Literal["wcgw", "architect"], CodeWriterMode]


class Initialize(BaseModel):
    type: Literal[
        "first_call",
        "user_asked_mode_change",
        "reset_shell",
        "user_asked_change_workspace",
    ]
    any_workspace_path: str
    initial_files_to_read: list[str]
    task_id_to_resume: str
    mode_name: Literal["wcgw", "architect", "code_writer"]
    thread_id: str = Field(
        description="Use the thread_id created in first_call, leave it as empty string if first_call"
    )
    code_writer_config: Optional[CodeWriterMode] = None

    def model_post_init(self, __context: Any) -> None:
        if self.mode_name == "code_writer":
            assert self.code_writer_config is not None, (
                "code_writer_config can't be null when the mode is code_writer"
            )
        return super().model_post_init(__context)

    @property
    def mode(self) -> ModesConfig:
        if self.mode_name == "wcgw":
            return "wcgw"
        if self.mode_name == "architect":
            return "architect"
        assert self.code_writer_config is not None, (
            "code_writer_config can't be null when the mode is code_writer"
        )
        return self.code_writer_config


class Command(BaseModel):
    command: str


class StatusCheck(BaseModel):
    status_check: Literal[True]


class SendText(BaseModel):
    send_text: str


Specials = Literal[
    "Enter", "Key-up", "Key-down", "Key-left", "Key-right", "Ctrl-c", "Ctrl-d"
]


class SendSpecials(BaseModel):
    send_specials: Sequence[Specials]


class SendAscii(BaseModel):
    send_ascii: Sequence[int]


class BashCommand(BaseModel):
    action_json: Command | StatusCheck | SendText | SendSpecials | SendAscii
    wait_for_seconds: Optional[float] = None
    thread_id: str


class ReadImage(BaseModel):
    file_path: str


class WriteIfEmpty(BaseModel):
    file_path: str
    file_content: str


class ReadFiles(BaseModel):
    file_paths: list[str]
    show_line_numbers_reason: Optional[str] = None
    _start_line_nums: List[Optional[int]] = PrivateAttr(default_factory=lambda: [])
    _end_line_nums: List[Optional[int]] = PrivateAttr(default_factory=lambda: [])

    @property
    def start_line_nums(self) -> List[Optional[int]]:
        """Get the start line numbers."""
        return self._start_line_nums

    @property
    def end_line_nums(self) -> List[Optional[int]]:
        """Get the end line numbers."""
        return self._end_line_nums

    def model_post_init(self, __context: Any) -> None:
        # Parse file paths for line ranges and store them in private attributes
        self._start_line_nums = []
        self._end_line_nums = []

        # Create new file_paths list without line ranges
        clean_file_paths = []

        for file_path in self.file_paths:
            start_line_num = None
            end_line_num = None
            path_part = file_path

            # Check if the path ends with a line range pattern
            # We're looking for patterns at the very end of the path like:
            #  - file.py:10      (specific line)
            #  - file.py:10-20   (line range)
            #  - file.py:10-     (from line 10 to end)
            #  - file.py:-20     (from start to line 20)

            # Split by the last colon
            if ":" in file_path:
                parts = file_path.rsplit(":", 1)
                if len(parts) == 2:
                    potential_path = parts[0]
                    line_spec = parts[1]

                    # Check if it's a valid line range format
                    if line_spec.isdigit():
                        # Format: file.py:10
                        try:
                            start_line_num = int(line_spec)
                            path_part = potential_path
                        except ValueError:
                            # Keep the original path if conversion fails
                            pass

                    elif "-" in line_spec:
                        # Could be file.py:10-20, file.py:10-, or file.py:-20
                        line_parts = line_spec.split("-", 1)

                        if not line_parts[0] and line_parts[1].isdigit():
                            # Format: file.py:-20
                            try:
                                end_line_num = int(line_parts[1])
                                path_part = potential_path
                            except ValueError:
                                # Keep original path
                                pass

                        elif line_parts[0].isdigit():
                            # Format: file.py:10-20 or file.py:10-
                            try:
                                start_line_num = int(line_parts[0])

                                if line_parts[1].isdigit():
                                    # file.py:10-20
                                    end_line_num = int(line_parts[1])

                                # In both cases, update the path
                                path_part = potential_path
                            except ValueError:
                                # Keep original path
                                pass

            # Add clean path and corresponding line numbers
            clean_file_paths.append(path_part)
            self._start_line_nums.append(start_line_num)
            self._end_line_nums.append(end_line_num)

        # Update file_paths with clean paths
        self.file_paths = clean_file_paths

        return super().model_post_init(__context)


class FileEdit(BaseModel):
    file_path: str
    file_edit_using_search_replace_blocks: str


class FileWriteOrEdit(BaseModel):
    # Naming should be in sorted order otherwise it gets changed in LLM backend.
    file_path: str = Field(description="#1: absolute file path")
    percentage_to_change: int = Field(
        description="#2: predict this percentage, calculated as number of existing lines that will have some diff divided by total existing lines."
    )
    text_or_search_replace_blocks: str = Field(
        description="#3: content/edit blocks. Must be after #2 in the tool xml"
    )
    thread_id: str = Field(description="#4: thread_id")


class ContextSave(BaseModel):
    id: str
    project_root_path: str
    description: str
    relevant_file_globs: list[str]


class Console(Protocol):
    def print(self, msg: str, *args: Any, **kwargs: Any) -> None: ...

    def log(self, msg: str, *args: Any, **kwargs: Any) -> None: ...


class Mdata(PydanticBaseModel):
    data: BashCommand | FileWriteOrEdit | str | ReadFiles | Initialize | ContextSave
