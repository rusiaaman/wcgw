import re
from typing import Callable

from .diff_edit import FileEditInput, FileEditOutput


def search_replace_edit(
    lines: list[str], original_content: str, logger: Callable[[str], object]
) -> tuple[str, str]:
    if not lines:
        raise Exception("Error: No input to search replace edit")
    original_lines = original_content.split("\n")
    n_lines = len(lines)
    i = 0
    search_replace_blocks = list[tuple[list[str], list[str]]]()
    while i < n_lines:
        if re.match(r"^<<<<<<+\s*SEARCH\s*$", lines[i]):
            search_block = []
            i += 1
            while i < n_lines and not re.match(r"^======*\s*$", lines[i]):
                search_block.append(lines[i])
                i += 1
            i += 1
            replace_block = []
            while i < n_lines and not re.match(r"^>>>>>>+\s*REPLACE\s*$", lines[i]):
                replace_block.append(lines[i])
                i += 1
            i += 1

            for line in search_block:
                logger("> " + line)
            logger("=======")
            for line in replace_block:
                logger("< " + line)
            logger("\n\n\n\n")

            search_replace_blocks.append((search_block, replace_block))
        else:
            i += 1

    if not search_replace_blocks:
        raise Exception(
            "No valid search replace blocks found, ensure your SEARCH/REPLACE blocks are formatted correctly"
        )

    fedit_input = FileEditInput(original_lines, 0, search_replace_blocks, 0)

    output = fedit_input.edit_file()
    best_matches, best_match_tolerance_hits = FileEditOutput.get_best_match(output)

    if best_match_tolerance_hits["ERROR"] > 0:
        best_matches[0].replace_or_throw(3)
        raise Exception("Something went wrong while editing")

    if len(best_matches) > 1:
        dup_match = FileEditOutput.find_block_matched_more_than_once(best_matches)
        raise Exception(f"""
The following block matched more than once:
---
```
{'\n'.join(dup_match)}
```
""")

    best_match = best_matches[0]

    edited_file, comments = best_match.replace_or_throw(3)
    if not comments:
        comments = "Edited successfully"
    else:
        comments = (
            "Edited successfully. However, following warnings were generated while matching search blocks.\n"
            + comments
        )
    return edited_file, comments
