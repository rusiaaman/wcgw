import re
from typing import Callable, Optional

from .diff_edit import FileEditInput, FileEditOutput, SearchReplaceMatchError

# Global regex patterns
SEARCH_MARKER = re.compile(r"^<<<<<<+\s*SEARCH\s*$")
DIVIDER_MARKER = re.compile(r"^======*\s*$")
REPLACE_MARKER = re.compile(r"^>>>>>>+\s*REPLACE\s*$")


class SearchReplaceSyntaxError(Exception):
    def __init__(self, message: str):
        message = f"""Got syntax error while parsing search replace blocks:
{message}
---

Make sure blocks are in correct sequence, and the markers are in separate lines:

<{"<<<<<< SEARCH"}
    example old
=======
    example new
>{">>>>>> REPLACE"}
 
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
                    raise SearchReplaceSyntaxError(
                        f"Line {i + 1}: Found stray marker in SEARCH block: {lines[i]}"
                    )
                search_block.append(lines[i])
                i += 1

            if i >= n_lines:
                raise SearchReplaceSyntaxError(
                    f"Line {line_num}: Unclosed SEARCH block - missing ======= marker"
                )

            if not search_block:
                raise SearchReplaceSyntaxError(
                    f"Line {line_num}: SEARCH block cannot be empty"
                )

            i += 1
            replace_block = []

            while i < n_lines and not REPLACE_MARKER.match(lines[i]):
                if SEARCH_MARKER.match(lines[i]) or DIVIDER_MARKER.match(lines[i]):
                    raise SearchReplaceSyntaxError(
                        f"Line {i + 1}: Found stray marker in REPLACE block: {lines[i]}"
                    )
                replace_block.append(lines[i])
                i += 1

            if i >= n_lines:
                raise SearchReplaceSyntaxError(
                    f"Line {line_num}: Unclosed block - missing REPLACE marker"
                )

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
                raise SearchReplaceSyntaxError(
                    f"Line {i + 1}: Found stray marker outside block: {lines[i]}"
                )
            i += 1

    if not search_replace_blocks:
        raise SearchReplaceSyntaxError(
            "No valid search replace blocks found, ensure your SEARCH/REPLACE blocks are formatted correctly"
        )

    edited_content, comments_ = edit_with_individual_fallback(
        original_lines, search_replace_blocks
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


def identify_first_differing_block(
    best_matches: list[FileEditOutput],
) -> Optional[list[str]]:
    """
    Identify the first search block that differs across multiple best matches.
    Returns the search block content that first shows different matches.
    """
    if not best_matches or len(best_matches) <= 1:
        return None

    # First, check if the number of blocks differs (shouldn't happen, but let's be safe)
    block_counts = [len(match.edited_with_tolerances) for match in best_matches]
    if not all(count == block_counts[0] for count in block_counts):
        # If block counts differ, just return the first search block as problematic
        return (
            best_matches[0].orig_search_blocks[0]
            if best_matches[0].orig_search_blocks
            else None
        )

    # Go through each block position and see if the slices differ
    for i in range(min(block_counts)):
        slices = [match.edited_with_tolerances[i][0] for match in best_matches]

        # Check if we have different slices for this block across matches
        if any(s.start != slices[0].start or s.stop != slices[0].stop for s in slices):
            # We found our differing block - return the search block content
            if i < len(best_matches[0].orig_search_blocks):
                return best_matches[0].orig_search_blocks[i]
            else:
                return None

    # If we get here, we couldn't identify a specific differing block
    return None


def edit_with_individual_fallback(
    original_lines: list[str], search_replace_blocks: list[tuple[list[str], list[str]]]
) -> tuple[list[str], set[str]]:
    outputs = FileEditInput(original_lines, 0, search_replace_blocks, 0).edit_file()
    best_matches = FileEditOutput.get_best_match(outputs)

    try:
        edited_content, comments_ = best_matches[0].replace_or_throw(3)
    except SearchReplaceMatchError:
        if len(search_replace_blocks) > 1:
            # Try one at a time
            all_comments = set[str]()
            running_lines = list(original_lines)
            for block in search_replace_blocks:
                running_lines, comments_ = edit_with_individual_fallback(
                    running_lines, [block]
                )
                all_comments |= comments_
            return running_lines, all_comments
        raise

    if len(best_matches) > 1:
        # Find the first block that differs across matches
        first_diff_block = identify_first_differing_block(best_matches)
        if first_diff_block is not None:
            block_content = "\n".join(first_diff_block)
            raise SearchReplaceMatchError(f"""
The following block matched more than once:
```
{block_content}
```
Consider adding more context before and after this block to make the match unique.
    """)
        else:
            raise SearchReplaceMatchError("""
One of the blocks matched more than once

Consider adding more context before and after all the blocks to make the match unique.
    """)

    return edited_content, comments_
