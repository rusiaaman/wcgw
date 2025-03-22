import os
from collections import deque
from pathlib import Path  # Still needed for other parts
from typing import Optional

from pygit2 import GitError, Repository
from pygit2.enums import SortMode

from .display_tree import DirectoryTree
from .file_stats import load_workspace_stats
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


def get_recent_git_files(repo: Repository, count: int = 10) -> list[str]:
    """
    Get the most recently modified files from git history

    Args:
        repo: The git repository
        count: Number of recent files to return

    Returns:
        List of relative paths to recently modified files
    """
    # Track seen files to avoid duplicates
    seen_files: set[str] = set()
    recent_files: list[str] = []

    try:
        # Get the HEAD reference and walk through recent commits
        head = repo.head
        for commit in repo.walk(head.target, SortMode.TOPOLOGICAL | SortMode.TIME):
            # Skip merge commits which have multiple parents
            if len(commit.parents) > 1:
                continue

            # If we have a parent, get the diff between the commit and its parent
            if commit.parents:
                parent = commit.parents[0]
                diff = repo.diff(parent, commit)  # type: ignore[attr-defined]
            else:
                # For the first commit, get the diff against an empty tree
                diff = commit.tree.diff_to_tree(context_lines=0)

            # Process each changed file in the diff
            for patch in diff:
                file_path = patch.delta.new_file.path

                # Skip if we've already seen this file or if the file was deleted
                repo_path_parent = Path(repo.path).parent
                if (
                    file_path in seen_files
                    or not (repo_path_parent / file_path).exists()
                ):
                    continue

                seen_files.add(file_path)
                recent_files.append(file_path)

                # If we have enough files, stop
                if len(recent_files) >= count:
                    return recent_files

    except Exception:
        # Handle git errors gracefully
        pass

    return recent_files


def calculate_dynamic_file_limit(total_files: int) -> int:
    # Scale linearly, with minimum and maximum bounds
    min_files = 50
    max_files = 400

    if total_files <= min_files:
        return min_files

    scale_factor = (max_files - min_files) / (30000 - min_files)

    dynamic_limit = min_files + int((total_files - min_files) * scale_factor)

    return min(max_files, dynamic_limit)


def get_repo_context(file_or_repo_path: str) -> tuple[str, Path]:
    file_or_repo_path_ = Path(file_or_repo_path).absolute()

    repo = find_ancestor_with_git(file_or_repo_path_)
    recent_git_files: list[str] = []

    # Determine the context directory
    if repo is not None:
        context_dir = Path(repo.path).parent
    else:
        if file_or_repo_path_.is_file():
            context_dir = file_or_repo_path_.parent
        else:
            context_dir = file_or_repo_path_

    # Load workspace stats from the context directory
    workspace_stats = load_workspace_stats(str(context_dir))

    # Get all files and calculate dynamic max files limit once
    all_files = get_all_files_max_depth(str(context_dir), 10, repo)

    # For Git repositories, get recent files
    if repo is not None:
        dynamic_max_files = calculate_dynamic_file_limit(len(all_files))
        # Get recent git files - get at least 10 or 20% of dynamic_max_files, whichever is larger
        recent_files_count = max(10, int(dynamic_max_files * 0.2))
        recent_git_files = get_recent_git_files(repo, recent_files_count)
    else:
        # We don't want dynamic limit for non git folders like /tmp or ~
        dynamic_max_files = 50

    # Calculate probabilities in batch
    path_scores = PATH_SCORER.calculate_path_probabilities_batch(all_files)

    # Create list of (path, score) tuples and sort by score
    path_with_scores = list(zip(all_files, (score[0] for score in path_scores)))
    sorted_files = [
        path for path, _ in sorted(path_with_scores, key=lambda x: x[1], reverse=True)
    ]

    # Start with recent git files, then add other important files
    top_files = []

    # If we have workspace stats, prioritize the most active files first
    active_files = []
    if workspace_stats is not None:
        # Get files with activity score (weighted count of operations)
        scored_files = []
        for file_path, file_stats in workspace_stats.files.items():
            try:
                # Convert to relative path if possible
                if str(context_dir) in file_path:
                    rel_path = os.path.relpath(file_path, str(context_dir))
                else:
                    rel_path = file_path

                # Calculate activity score - weight reads more for this functionality
                activity_score = (
                    file_stats.read_count * 2
                    + (file_stats.edit_count)
                    + (file_stats.write_count)
                )

                # Only include files that still exist
                if rel_path in all_files or os.path.exists(file_path):
                    scored_files.append((rel_path, activity_score))
            except (ValueError, OSError):
                # Skip files that cause path resolution errors
                continue

        # Sort by activity score (highest first) and get top 5
        active_files = [
            f for f, _ in sorted(scored_files, key=lambda x: x[1], reverse=True)[:5]
        ]

        # Add active files first
        for file in active_files:
            if file not in top_files and file in all_files:
                top_files.append(file)

    # Add recent git files next - these should be prioritized
    for file in recent_git_files:
        if file not in top_files and file in all_files:
            top_files.append(file)

    # Use statistical sorting for the remaining files, but respect dynamic_max_files limit
    # and ensure we don't add duplicates
    if len(top_files) < dynamic_max_files:
        # Only add statistically important files that aren't already in top_files
        for file in sorted_files:
            if file not in top_files and len(top_files) < dynamic_max_files:
                top_files.append(file)

    directory_printer = DirectoryTree(context_dir, max_files=dynamic_max_files)
    for file in top_files[:dynamic_max_files]:
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
    result = get_repo_context(folder)[0]
    profiler.disable()

    # Print cProfile stats
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    print("\n=== Function-level profiling ===")
    stats.print_stats(20)  # Print top 20 functions

    # Profile using line_profiler for line-by-line statistics
    lp = LineProfiler()
    lp_wrapper = lp(get_repo_context)
    lp_wrapper(folder)

    print("\n=== Line-by-line profiling ===")
    lp.print_stats()

    print("\n=== Result ===")
    print(result)
