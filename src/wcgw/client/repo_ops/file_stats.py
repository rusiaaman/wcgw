import hashlib
import json
import os
import sys
from typing import Any, Callable, Dict, TypeVar, cast

T = TypeVar("T")  # Type variable for generic functions
F = TypeVar("F", bound=Callable[..., Any])  # Type variable for decorated functions


class FileStats:
    """Track read, edit, and write counts for a single file."""

    def __init__(self) -> None:
        self.read_count: int = 0
        self.edit_count: int = 0
        self.write_count: int = 0

    def increment_read(self) -> None:
        """Increment the read counter."""
        self.read_count += 1

    def increment_edit(self) -> None:
        """Increment the edit counter."""
        self.edit_count += 1

    def increment_write(self) -> None:
        """Increment the write counter."""
        self.write_count += 1

    def to_dict(self) -> Dict[str, int]:
        """Convert to a dictionary for serialization."""
        return {
            "read_count": self.read_count,
            "edit_count": self.edit_count,
            "write_count": self.write_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileStats":
        """Create from a serialized dictionary."""
        stats = cls()
        stats.read_count = data.get("read_count", 0)
        stats.edit_count = data.get("edit_count", 0)
        stats.write_count = data.get("write_count", 0)
        return stats


class WorkspaceStats:
    """Track file operations statistics for an entire workspace."""

    def __init__(self) -> None:
        self.files: Dict[str, FileStats] = {}  # filepath -> FileStats

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for serialization."""
        return {"files": {k: v.to_dict() for k, v in self.files.items()}}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkspaceStats":
        """Create from a serialized dictionary."""
        stats = cls()
        files_data = data.get("files", {})
        stats.files = {k: FileStats.from_dict(v) for k, v in files_data.items()}
        return stats


def safe_stats_operation(func: F) -> F:
    """
    Decorator to safely perform stats operations without affecting core functionality.
    If an exception occurs, it logs the error but allows the program to continue.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Log the error but continue with the operation
            print(f"Warning: Stats tracking error - {e}", file=sys.stderr)
            return None

    # This is a workaround for proper typing with decorators
    return cast(F, wrapper)


def get_stats_path(workspace_path: str) -> str:
    """
    Get the path to the stats file for a workspace using a hash-based approach.

    Args:
        workspace_path: The full path of the workspace directory.

    Returns:
        The path to the stats file.
    """
    # Normalize the path
    workspace_path = os.path.normpath(os.path.expanduser(workspace_path))

    # Get the basename of the workspace path for readability
    workspace_name = os.path.basename(workspace_path)
    if not workspace_name:  # In case of root directory
        workspace_name = "root"

    # Create a hash of the full path
    path_hash = hashlib.md5(workspace_path.encode()).hexdigest()

    # Combine to create a unique identifier that's still somewhat readable
    filename = f"{workspace_name}_{path_hash}.json"

    # Create directory if it doesn't exist
    xdg_data_dir = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    stats_dir = os.path.join(xdg_data_dir, "wcgw/workspace_stats")
    os.makedirs(stats_dir, exist_ok=True)

    return os.path.join(stats_dir, filename)


@safe_stats_operation
def load_workspace_stats(workspace_path: str) -> WorkspaceStats:
    """
    Load the stats for a workspace, or create empty stats if not exists.

    Args:
        workspace_path: The full path of the workspace directory.

    Returns:
        WorkspaceStats object containing file operation statistics.
    """
    stats_path = get_stats_path(workspace_path)
    if os.path.exists(stats_path):
        try:
            with open(stats_path, "r") as f:
                return WorkspaceStats.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError, ValueError):
            # Handle corrupted file
            return WorkspaceStats()
    else:
        return WorkspaceStats()


@safe_stats_operation
def save_workspace_stats(workspace_path: str, stats: WorkspaceStats) -> None:
    """
    Save the stats for a workspace.

    Args:
        workspace_path: The full path of the workspace directory.
        stats: WorkspaceStats object to save.
    """
    stats_path = get_stats_path(workspace_path)
    with open(stats_path, "w") as f:
        json.dump(stats.to_dict(), f, indent=2)
