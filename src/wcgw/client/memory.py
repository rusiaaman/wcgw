import os
import re
import shlex
from typing import Callable, Optional

from ..types_ import ContextSave


def get_app_dir_xdg() -> str:
    xdg_data_dir = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(xdg_data_dir, "wcgw")


def format_memory(task_memory: ContextSave, relevant_files: str) -> str:
    memory_data = ""
    if task_memory.project_root_path:
        memory_data += (
            f"# PROJECT ROOT = {shlex.quote(task_memory.project_root_path)}\n"
        )
    memory_data += task_memory.description

    memory_data += (
        "\n\n"
        + "# Relevant file paths\n"
        + ", ".join(map(shlex.quote, task_memory.relevant_file_globs))
    )

    memory_data += "\n\n# Relevant Files:\n" + relevant_files

    return memory_data


def save_memory(task_memory: ContextSave, relevant_files: str) -> str:
    app_dir = get_app_dir_xdg()
    memory_dir = os.path.join(app_dir, "memory")
    os.makedirs(memory_dir, exist_ok=True)

    task_id = task_memory.id
    if not task_id:
        raise Exception("Task id can not be empty")
    memory_data = format_memory(task_memory, relevant_files)

    memory_file_full = os.path.join(memory_dir, f"{task_id}.txt")

    with open(memory_file_full, "w") as f:
        f.write(memory_data)

    return memory_file_full


def load_memory[T](
    task_id: str,
    max_tokens: Optional[int],
    encoder: Callable[[str], list[T]],
    decoder: Callable[[list[T]], str],
) -> tuple[str, str]:
    app_dir = get_app_dir_xdg()
    memory_dir = os.path.join(app_dir, "memory")
    memory_file = os.path.join(memory_dir, f"{task_id}.txt")

    with open(memory_file, "r") as f:
        data = f.read()

    if max_tokens:
        toks = encoder(data)
        if len(toks) > max_tokens:
            toks = toks[: max(0, max_tokens - 10)]
            data = decoder(toks)
            data += "\n(... truncated)"

    project_root_match = re.search(r"# PROJECT ROOT = \s*(.*?)\s*$", data, re.MULTILINE)
    project_root_path = ""
    if project_root_match:
        matched_path = project_root_match.group(1)
        parsed_ = shlex.split(matched_path)
        if parsed_ and len(parsed_) == 1:
            project_root_path = parsed_[0]
    return project_root_path, data
