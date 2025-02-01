import re
from typing import Callable

from .diff_edit import FileEditInput, FileEditOutput, SearchReplaceMatchError

# Global regex patterns
SEARCH_MARKER = re.compile(r"^<<<<<<+\s*SEARCH\s*$")
DIVIDER_MARKER = re.compile(r"^======*\s*$") 
REPLACE_MARKER = re.compile(r"^>>>>>>+\s*REPLACE\s*$")

class SearchReplaceSyntaxError(Exception):
    def __init__(self, message: str):
        message =f"""Got syntax error while parsing search replace blocks:
{message}
---

Make sure blocks are in correct sequence, and the markers are in separate lines:

<{'<<<<<< SEARCH'}
    example old
=======
    example new
>{'>>>>>> REPLACE'}
 
"""
        super().__init__(message)

def search_replace_edit(
    lines: list[str], original_content: str, logger: Callable[[str], object]
) -> tuple[str, str]:
    if not lines:
        raise SearchReplaceSyntaxError("Error: No input to search replace edit")
    
    original_lines = original_content.split("\n")
    n_lines = len(lines)
    i = 0
    search_replace_blocks = list[tuple[list[str], list[str]]]()
    
    while i < n_lines:
        if SEARCH_MARKER.match(lines[i]):
            line_num = i + 1
            search_block = []
            i += 1
            
            while i < n_lines and not DIVIDER_MARKER.match(lines[i]):
                if SEARCH_MARKER.match(lines[i]) or REPLACE_MARKER.match(lines[i]):
                    raise SearchReplaceSyntaxError(f"Line {i+1}: Found stray marker in SEARCH block: {lines[i]}")
                search_block.append(lines[i])
                i += 1
            
            if i >= n_lines:
                raise SearchReplaceSyntaxError(f"Line {line_num}: Unclosed SEARCH block - missing ======= marker")
            
            if not search_block:
                raise SearchReplaceSyntaxError(f"Line {line_num}: SEARCH block cannot be empty")
            
            i += 1
            replace_block = []
            
            while i < n_lines and not REPLACE_MARKER.match(lines[i]):
                if SEARCH_MARKER.match(lines[i]) or DIVIDER_MARKER.match(lines[i]):
                    raise SearchReplaceSyntaxError(f"Line {i+1}: Found stray marker in REPLACE block: {lines[i]}")
                replace_block.append(lines[i])
                i += 1
            
            if i >= n_lines:
                raise SearchReplaceSyntaxError(f"Line {line_num}: Unclosed block - missing REPLACE marker")
            
            i += 1

            for line in search_block:
                logger("> " + line)
            logger("=======")
            for line in replace_block:
                logger("< " + line)
            logger("\n\n\n\n")

            search_replace_blocks.append((search_block, replace_block))
        else:
            if REPLACE_MARKER.match(lines[i]) or DIVIDER_MARKER.match(lines[i]):
                raise SearchReplaceSyntaxError(f"Line {i+1}: Found stray marker outside block: {lines[i]}")
            i += 1

    if not search_replace_blocks:
        raise SearchReplaceSyntaxError(
            "No valid search replace blocks found, ensure your SEARCH/REPLACE blocks are formatted correctly"
        )

    edited_content, comments_ = greedy_context_replace(
        original_lines, [[x] for x in search_replace_blocks], original_lines, set(), 0
    )
    edited_file = "\n".join(edited_content)
    if not comments_:
        comments = "Edited successfully"
    else:
        comments = (
            "Edited successfully. However, following warnings were generated while matching search blocks.\n"
            + "\n".join(comments_)
        )
    return edited_file, comments


def greedy_context_replace(
    original_lines: list[str],
    search_replace_blocks: list[list[tuple[list[str], list[str]]]],
    running_lines: list[str],
    running_comments: set[str],
    current_block_offset: int,
) -> tuple[list[str], set[str]]:
    if current_block_offset >= len(search_replace_blocks):
        return running_lines, running_comments
    current_blocks = search_replace_blocks[current_block_offset]

    outputs = FileEditInput(running_lines, 0, current_blocks, 0).edit_file()
    best_matches, is_error = FileEditOutput.get_best_match(outputs)

    if is_error:
        best_matches[0].replace_or_throw(3)
        raise Exception("Shouldn't happen")

    if len(best_matches) > 1:
        # Duplicate found, try to ground using previous blocks.
        if current_block_offset == 0:
            raise SearchReplaceMatchError(f"""
    The following block matched more than once:
    ---
    ```
    {'\n'.join(current_blocks[-1][0])}
    ```
    """)

        else:
            search_replace_blocks = (
                search_replace_blocks[: current_block_offset - 1]
                + [search_replace_blocks[current_block_offset - 1] + current_blocks]
                + search_replace_blocks[current_block_offset + 1 :]
            )
            try:
                return greedy_context_replace(
                    original_lines, search_replace_blocks, original_lines, set(), 0
                )
            except Exception:
                raise Exception(f"""
        The following block matched more than once:
        ---
        ```
        {'\n'.join(current_blocks[-1][0])}
        ```
        """)

    best_match = best_matches[0]
    running_lines, comments = best_match.replace_or_throw(3)
    running_comments = running_comments | comments
    return greedy_context_replace(
        original_lines,
        search_replace_blocks,
        running_lines,
        running_comments,
        current_block_offset + 1,
    )
