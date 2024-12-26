import os
from collections import deque
from pathlib import Path  # Still needed for other parts
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


MAX_ENTRIES_CHECK = 100_000


def get_all_files_max_depth(
    abs_folder: str,
    max_depth: int,
    repo: Optional[Repository],
) -> list[str]:
    """BFS implementation using deque that maintains relative paths during traversal.
    Returns (files_list, total_files_found) to track file count."""
    all_files = []
    # Queue stores: (folder_path, depth, rel_path_prefix)
    queue = deque([(abs_folder, 0, "")])
    entries_check = 0
    while queue and entries_check < MAX_ENTRIES_CHECK:
        current_folder, depth, prefix = queue.popleft()

        if depth > max_depth:
            continue

        try:
            entries = list(os.scandir(current_folder))
        except PermissionError:
            continue
        except OSError:
            continue
        # Split into files and folders with single scan
        files = []
        folders = []
        for entry in entries:
            entries_check += 1
            try:
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                continue
            name = entry.name
            rel_path = f"{prefix}{name}" if prefix else name

            if repo and repo.path_is_ignored(rel_path):
                continue

            if is_file:
                files.append(rel_path)
            else:
                folders.append((entry.path, rel_path))

        # Process files first (maintain priority)
        chunk = files[: min(10_000, max(0, MAX_ENTRIES_CHECK - entries_check))]
        all_files.extend(chunk)

        # Add folders to queue for BFS traversal
        for folder_path, folder_rel_path in folders:
            next_prefix = f"{folder_rel_path}/"
            queue.append((folder_path, depth + 1, next_prefix))

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

    all_files = get_all_files_max_depth(str(context_dir), 10, repo)

    # Calculate probabilities in batch
    path_scores = PATH_SCORER.calculate_path_probabilities_batch(all_files)

    # Create list of (path, score) tuples and sort by score
    path_with_scores = list(zip(all_files, (score[0] for score in path_scores)))
    sorted_files = [
        path for path, _ in sorted(path_with_scores, key=lambda x: x[1], reverse=True)
    ]

    top_files = sorted_files[:max_files]

    directory_printer = DirectoryTree(context_dir, max_files=max_files)
    for file in top_files:
        directory_printer.expand(file)

    return directory_printer.display(), context_dir


if __name__ == "__main__":
    import cProfile
    import pstats
    import sys

    from line_profiler import LineProfiler

    folder = sys.argv[1]

    # Profile using cProfile for overall function statistics
    profiler = cProfile.Profile()
    profiler.enable()
    result = get_repo_context(folder, 200)[0]
    profiler.disable()

    # Print cProfile stats
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    print("\n=== Function-level profiling ===")
    stats.print_stats(20)  # Print top 20 functions

    # Profile using line_profiler for line-by-line statistics
    lp = LineProfiler()
    lp_wrapper = lp(get_repo_context)
    lp_wrapper(folder, 200)

    print("\n=== Line-by-line profiling ===")
    lp.print_stats()

    print("\n=== Result ===")
    print(result)
