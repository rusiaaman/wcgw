from pathlib import Path
from typing import Optional

from pygit2 import GitError, Repository

from .display_tree import DirectoryTree
from .path_prob import FastPathAnalyzer

curr_folder = Path(__file__).parent
vocab_file = curr_folder / "paths_model.vocab"
model_file = curr_folder / "paths_tokens.model"
PATH_SCORER = FastPathAnalyzer(str(model_file), str(vocab_file))


def find_ancestor_with_git(path: Path) -> Optional[Repository]:
    if path.is_file():
        path = path.parent

    try:
        return Repository(str(path))
    except GitError:
        return None


def get_all_files_max_depth(
    folder: Path,
    max_depth: int,
    rel_to: str,
    repo: Optional[Repository],
    current_depth: int,
) -> list[str]:
    if current_depth > max_depth:
        return []

    all_files = []
    for child in folder.iterdir():
        rel_path = str(child.relative_to(rel_to))
        if repo and repo.path_is_ignored(rel_path):
            continue

        if child.is_file():
            all_files.append(rel_path)
        elif child.is_dir():
            all_files.extend(
                get_all_files_max_depth(
                    child, max_depth, rel_to, repo, current_depth + 1
                )
            )

    return all_files


def get_repo_context(file_or_repo_path: str, max_files: int) -> tuple[str, Path]:
    file_or_repo_path_ = Path(file_or_repo_path).absolute()

    repo = find_ancestor_with_git(file_or_repo_path_)

    if repo is not None:
        context_dir = Path(repo.path).parent
    else:
        if file_or_repo_path_.is_file():
            context_dir = file_or_repo_path_.parent
        else:
            context_dir = file_or_repo_path_

    all_files = get_all_files_max_depth(context_dir, 10, str(context_dir), repo, 0)

    sorted_files = sorted(
        all_files,
        key=lambda x: PATH_SCORER.calculate_path_probability(x)[0],
        reverse=True,
    )

    top_files = sorted_files[:max_files]

    directory_printer = DirectoryTree(context_dir, max_files=max_files)

    for file in top_files:
        directory_printer.expand(file)

    return directory_printer.display(), context_dir


if __name__ == "__main__":
    import sys

    folder = sys.argv[1]
    print(get_repo_context(folder, 200)[0])
