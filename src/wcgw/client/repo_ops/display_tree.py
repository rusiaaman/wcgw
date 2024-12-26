import io
from pathlib import Path
from typing import List, Set


class DirectoryTree:
    def __init__(self, root: Path, max_files: int = 10):
        """
        Initialize the DirectoryTree with a root path and maximum number of files to display

        Args:
            root_path: The root directory path to start from
            max_files: Maximum number of files to display in unexpanded directories
        """
        self.root = root
        self.max_files = max_files
        self.expanded_files: Set[Path] = set()
        self.expanded_dirs = set[Path]()

        if not self.root.exists():
            raise ValueError(f"Root path {root} does not exist")

        if not self.root.is_dir():
            raise ValueError(f"Root path {root} is not a directory")

    def expand(self, rel_path: str) -> None:
        """
        Expand a specific file in the tree

        Args:
            rel_path: Relative path from root to the file to expand
        """
        abs_path = self.root / rel_path

        if not abs_path.exists():
            raise ValueError(f"Path {rel_path} does not exist")

        if not abs_path.is_file():
            raise ValueError(f"Path {rel_path} is not a file")

        if not str(abs_path).startswith(str(self.root)):
            raise ValueError(f"Path {rel_path} is outside root directory")

        self.expanded_files.add(abs_path)

        # Add all parent directories to expanded dirs
        current = abs_path.parent
        while str(current) >= str(self.root):
            if current not in self.expanded_dirs:
                self.expanded_dirs.add(current)
            if current == current.parent:
                break
            current = current.parent

    def _list_directory(self, dir_path: Path) -> List[Path]:
        """List contents of a directory, sorted with directories first"""
        contents = list(dir_path.iterdir())
        return sorted(contents, key=lambda x: (not x.is_dir(), x.name.lower()))

    def _count_hidden_items(
        self, dir_path: Path, shown_items: List[Path]
    ) -> tuple[int, int]:
        """Count hidden files and directories in a directory"""
        all_items = set(self._list_directory(dir_path))
        shown_items_set = set(shown_items)
        hidden_items = all_items - shown_items_set

        hidden_files = sum(1 for p in hidden_items if p.is_file())
        hidden_dirs = sum(1 for p in hidden_items if p.is_dir())

        return hidden_files, hidden_dirs

    def display(self) -> str:
        """Display the directory tree with expanded state"""
        writer = io.StringIO()

        def _display_recursive(
            current_path: Path, indent: int = 0, depth: int = 0
        ) -> None:
            # Print current directory name
            if current_path == self.root:
                writer.write(f"{current_path}\n")
            else:
                writer.write(f"{' ' * indent}{current_path.name}\n")

            # Don't recurse beyond depth 1 unless path contains expanded files
            if depth > 0 and current_path not in self.expanded_dirs:
                return

            # Get directory contents
            contents = self._list_directory(current_path)
            shown_items = []

            for item in contents:
                # Show items only if:
                # 1. They are expanded files
                # 2. They are parents of expanded items
                should_show = item in self.expanded_files or item in self.expanded_dirs

                if should_show:
                    shown_items.append(item)
                    if item.is_dir():
                        _display_recursive(item, indent + 2, depth + 1)
                    else:
                        writer.write(f"{' ' * (indent + 2)}{item.name}\n")

            # Show hidden items count if any items were hidden
            hidden_files, hidden_dirs = self._count_hidden_items(
                current_path, shown_items
            )
            if hidden_files > 0 or hidden_dirs > 0:
                hidden_msg = []
                if hidden_dirs > 0:
                    hidden_msg.append(
                        f"{hidden_dirs} director{'ies' if hidden_dirs != 1 else 'y'}"
                    )
                if hidden_files > 0:
                    hidden_msg.append(
                        f"{hidden_files} file{'s' if hidden_files != 1 else ''}"
                    )
                writer.write(
                    f"{' ' * (indent + 2)}... {' and '.join(hidden_msg)} hidden\n"
                )

        _display_recursive(self.root, depth=0)

        return writer.getvalue()
