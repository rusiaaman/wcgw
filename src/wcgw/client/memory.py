import os

from ..types_ import KnowledgeTransfer


def get_app_dir_xdg() -> str:
    xdg_data_dir = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(xdg_data_dir, "wcgw")


def format_memory(task_memory: KnowledgeTransfer, relevant_files: str) -> str:
    memory_data = f"""# Goal: {task_memory.objective}\n\n
# Instructions:\n{task_memory.all_user_instructions}\n\n
# Current Status:\n{task_memory.current_status_of_the_task}\n\n
# Pending Issues:\n{task_memory.all_issues_snippets}\n\n
# Build Instructions:\n{task_memory.build_and_development_instructions}\n"""

    memory_data += "\n# Relevant Files:\n" + relevant_files

    return memory_data


def save_memory(task_memory: KnowledgeTransfer, relevant_files: str) -> str:
    app_dir = get_app_dir_xdg()
    memory_dir = os.path.join(app_dir, "memory")
    os.makedirs(memory_dir, exist_ok=True)

    task_id = task_memory.id
    if not task_id:
        raise Exception("Task id can not be empty")
    memory_data = format_memory(task_memory, relevant_files)

    memory_file = os.path.join(memory_dir, f"{task_id}.json")
    memory_file_full = os.path.join(memory_dir, f"{task_id}.txt")

    with open(memory_file_full, "w") as f:
        f.write(memory_data)

    with open(memory_file, "w") as f:
        f.write(task_memory.model_dump_json())

    return memory_file_full


def load_memory(task_id: str) -> KnowledgeTransfer:
    app_dir = get_app_dir_xdg()
    memory_dir = os.path.join(app_dir, "memory")
    memory_file = os.path.join(memory_dir, f"{task_id}.json")

    with open(memory_file, "r") as f:
        task_save = KnowledgeTransfer.model_validate_json(f.read())
    return task_save
