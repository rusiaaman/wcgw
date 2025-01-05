import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable, DefaultDict, Literal, Optional

TOLERANCE_TYPES = Literal["SILENT", "WARNING", "ERROR"]


@dataclass
class Tolerance:
    line_process: Callable[[str], str]
    severity_cat: TOLERANCE_TYPES
    score_multiplier: float
    error_name: str


@dataclass
class TolerancesHit(Tolerance):
    count: int


@dataclass
class FileEditOutput:
    original_content: list[str]
    orig_search_blocks: list[list[str]]
    edited_with_tolerances: list[tuple[slice, list[TolerancesHit], list[str]]]

    def replace_or_throw(
        self,
        max_errors: int,
    ) -> tuple[list[str], set[str]]:
        new_lines = list[str]()
        last_idx = 0
        errors = []
        warnings = set[str]()
        for (span, tolerances, replace_with), search_ in zip(
            self.edited_with_tolerances, self.orig_search_blocks
        ):
            for tol in tolerances:
                if tol.count > 0:
                    if tol.severity_cat == "WARNING":
                        warnings.add(tol.error_name)
                    elif tol.severity_cat == "ERROR":
                        errors.append(f"""
Got error while processing the following search block:
---
```
{'\n'.join(search_)}
```
---
Error:
{tol.error_name}
---
                                  """)
                    if len(errors) >= max_errors:
                        raise Exception("\n".join(errors))
            if last_idx < span.start:
                new_lines.extend(self.original_content[last_idx : span.start])

            new_lines.extend(replace_with)
            last_idx = span.stop

        if last_idx < len(self.original_content):
            new_lines.extend(self.original_content[last_idx:])

        if errors:
            raise Exception("\n".join(errors))

        return new_lines, set(warnings)

    @staticmethod
    def get_best_match(
        outputs: list["FileEditOutput"],
    ) -> tuple[list["FileEditOutput"], bool]:
        best_hits: list[FileEditOutput] = []
        best_score = float("-inf")
        assert outputs
        for output in outputs:
            hit_score = 0.0
            for _, tols, _ in output.edited_with_tolerances:
                for tol in tols:
                    hit_score += tol.count * tol.score_multiplier
            if not best_hits:
                best_hits.append(output)
                best_score = hit_score
            else:
                if hit_score < best_score:
                    best_hits = [output]
                    best_score = hit_score
                elif abs(hit_score - best_score) < 1e-3:
                    best_hits.append(output)

        return best_hits, best_score < 0


def line_process_max_space_tolerance(line: str) -> str:
    line = line.strip()
    return re.sub(r"\s", "", line)


DEFAULT_TOLERANCES = [
    Tolerance(
        line_process=str.rstrip,
        severity_cat="SILENT",
        score_multiplier=1,
        error_name="",
    ),
    Tolerance(
        line_process=str.lstrip,
        severity_cat="WARNING",
        score_multiplier=10,
        error_name="Warning: matching without considering indentation (leading spaces).",
    ),
    Tolerance(
        line_process=line_process_max_space_tolerance,
        severity_cat="WARNING",
        score_multiplier=50,
        error_name="Warning: matching after removing all spaces in lines.",
    ),
]


def remove_leading_trailing_empty_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines) - 1
    if end < start:
        return lines
    while not lines[start].strip():
        start += 1
        if start >= len(lines):
            break
    while not lines[end].strip():
        end -= 1
        if end < 0:
            break
    return lines[start : end + 1]


@dataclass
class FileEditInput:
    file_lines: list[str]
    file_line_offset: int
    search_replace_blocks: list[tuple[list[str], list[str]]]
    search_replace_offset: int
    tolerances: list["Tolerance"] = field(default_factory=lambda: DEFAULT_TOLERANCES)

    def edit_file(self) -> list[FileEditOutput]:
        n_file_lines = len(self.file_lines)
        n_blocks = len(self.search_replace_blocks)

        # Boundary conditions
        no_match_output = FileEditOutput(
            original_content=self.file_lines,
            orig_search_blocks=[x[0] for x in self.search_replace_blocks],
            edited_with_tolerances=[
                (
                    slice(0, 0),
                    [
                        TolerancesHit(
                            line_process=lambda x: x,
                            severity_cat="ERROR",
                            score_multiplier=float("-inf"),
                            error_name="The blocks couldn't be matched, maybe the sequence of search blocks was incorrect?",
                            count=max(1, len(search_lines)),
                        )
                        for search_lines, _ in self.search_replace_blocks[
                            self.search_replace_offset :
                        ]
                    ],
                    [],
                )
            ],
        )
        if (
            self.file_line_offset >= n_file_lines
            and self.search_replace_offset < n_blocks
        ):
            return [no_match_output]
        elif self.file_line_offset >= n_file_lines:
            return [
                FileEditOutput(
                    self.file_lines,
                    [x[0] for x in self.search_replace_blocks],
                    [(slice(0, 0), [], [])],
                )
            ]
        elif self.search_replace_offset >= n_blocks:
            return [
                FileEditOutput(
                    self.file_lines,
                    [x[0] for x in self.search_replace_blocks],
                    [(slice(0, 0), [], [])],
                )
            ]

        # search for first block
        first_block = self.search_replace_blocks[self.search_replace_offset]

        # Try exact match
        matches = match_exact(self.file_lines, self.file_line_offset, first_block[0])

        all_outputs = list[list[tuple[slice, list[TolerancesHit], list[str]]]]()

        if not matches:
            # Try tolerances
            matches_with_tolerances = match_with_tolerance(
                self.file_lines, self.file_line_offset, first_block[0], self.tolerances
            )
            replace_by = first_block[1]
            if not matches_with_tolerances:
                # Try with no empty lines
                matches_with_tolerances = match_with_tolerance_empty_line(
                    self.file_lines,
                    self.file_line_offset,
                    first_block[0],
                    self.tolerances,
                )
                replace_by = remove_leading_trailing_empty_lines(first_block[1])

                if not matches_with_tolerances:
                    # Report edit distance
                    sim_match, sim_sim, sim_context = (
                        find_least_edit_distance_substring(
                            self.file_lines, self.file_line_offset, first_block[0]
                        )
                    )
                    if sim_match:
                        matches_with_tolerances = [
                            (
                                sim_match,
                                [
                                    TolerancesHit(
                                        lambda x: x,
                                        "ERROR",
                                        -1,
                                        "Couldn't find match. Do you mean to match the lines in the following context?\n```"
                                        + sim_context
                                        + "\n```",
                                        int(len(first_block[0]) // sim_sim),
                                    )
                                ],
                            )
                        ]

            for match, tolerances in matches_with_tolerances:
                file_edit_input = FileEditInput(
                    self.file_lines,
                    match.stop,
                    self.search_replace_blocks,
                    self.search_replace_offset + 1,
                    self.tolerances,
                )

                remaining_output = file_edit_input.edit_file()
                for rem_output in remaining_output:
                    all_outputs.append(
                        [
                            (match, tolerances, replace_by),
                            *rem_output.edited_with_tolerances,
                        ]
                    )
        else:
            for match in matches:
                file_edit_input = FileEditInput(
                    self.file_lines,
                    match.stop,
                    self.search_replace_blocks,
                    self.search_replace_offset + 1,
                    self.tolerances,
                )
                remaining_output = file_edit_input.edit_file()
                for rem_output in remaining_output:
                    all_outputs.append(
                        [
                            (
                                match,
                                [],
                                first_block[1],
                            ),
                            *rem_output.edited_with_tolerances,
                        ]
                    )

        if not all_outputs:
            return [no_match_output]

        return [
            FileEditOutput(
                self.file_lines, [x[0] for x in self.search_replace_blocks], output
            )
            for output in all_outputs
        ]


def find_contiguous_match(search_line_positions: list[set[int]]) -> list[slice]:
    n_search_lines = len(search_line_positions)

    def search_in_dictionary(search_offset: int, search_index: int) -> bool:
        if search_offset >= n_search_lines:
            return True

        if search_index in search_line_positions[search_offset]:
            return search_in_dictionary(search_offset + 1, search_index + 1)
        return False

    matched_slices = []
    for index in search_line_positions[0]:
        if search_in_dictionary(1, index + 1):
            matched_slices.append(slice(index, index + n_search_lines, 1))
    return matched_slices


def match_exact(
    content: list[str], content_offset: int, search: list[str]
) -> list[slice]:
    n_search_lines = len(search)
    n_content = len(content) - content_offset
    if n_search_lines > n_content:
        return []
    if n_search_lines == 0:
        return []
    if n_content == 0:
        return []
    content_positions = DefaultDict[str, set[int]](set)
    for i in range(content_offset, n_content):
        content_positions[content[i]].add(i)
    search_line_positions = [content_positions[line] for line in search]

    matched_slices = find_contiguous_match(search_line_positions)

    return matched_slices


def match_with_tolerance(
    content: list[str],
    content_offset: int,
    search: list[str],
    tolerances: list[Tolerance],
) -> list[tuple[slice, list[TolerancesHit]]]:
    n_search_lines = len(search)
    n_content = len(content) - content_offset
    if n_search_lines > n_content:
        return []
    if n_search_lines == 0:
        return []
    if n_content == 0:
        return []
    content_positions = DefaultDict[str, set[int]](set)
    for i in range(content_offset, n_content):
        content_positions[content[i]].add(i)
    search_line_positions = [content_positions[line] for line in search]

    tolerance_index_by_content_line: list[dict[int, int]] = [
        {} for _ in range(len(search))
    ]
    for tidx, tolerance in enumerate(tolerances):
        content_positions = DefaultDict[str, set[int]](set)
        for i in range(content_offset, n_content):
            line = content[i]
            content_positions[tolerance.line_process(line)].add(i)
        for i, line in enumerate(search):
            new_lines = content_positions[tolerance.line_process(line)]
            new_indices = new_lines - search_line_positions[i]
            search_line_positions[i].update(new_indices)
            tolerance_index_by_content_line[i].update(
                {idx: tidx for idx in new_indices}
            )
    matched_slices = find_contiguous_match(search_line_positions)

    tolerances_counts: list[list[TolerancesHit]] = [
        [
            TolerancesHit(
                line_process=tol.line_process,
                severity_cat=tol.severity_cat,
                score_multiplier=tol.score_multiplier,
                count=0,
                error_name=tol.error_name,
            )
            for tol in tolerances
        ]
        for _ in range(len(matched_slices))
    ]
    for sidx, slice in enumerate(matched_slices):
        for search_idx, content_idx in enumerate(
            range(slice.start, slice.stop, slice.step)
        ):
            if content_idx in tolerance_index_by_content_line[search_idx]:
                tolerances_counts[sidx][
                    tolerance_index_by_content_line[search_idx][content_idx]
                ].count += 1

    return list(zip(matched_slices, tolerances_counts))


def match_with_tolerance_empty_line(
    content: list[str],
    content_offset: int,
    search: list[str],
    tolerances: list[Tolerance],
) -> list[tuple[slice, list[TolerancesHit]]]:
    new_content = list[str]()
    new_to_original = dict[int, int]()
    for i in range(content_offset, len(content)):
        line = content[i]
        if line.strip():
            new_to_original[len(new_content)] = i
            new_content.append(line)

    search = [line for line in search if line.strip()]

    matches_with_tolerancs = match_with_tolerance(new_content, 0, search, tolerances)

    new_matches_with_tolerances = list[tuple[slice, list[TolerancesHit]]]()
    for matches, tolerance_counts in matches_with_tolerancs:
        matches = slice(
            new_to_original[matches.start], new_to_original[matches.stop - 1] + 1, 1
        )
        new_matches_with_tolerances.append((matches, tolerance_counts))
    return new_matches_with_tolerances


def find_least_edit_distance_substring(
    orig_content_lines: list[str], offset: int, find_lines: list[str]
) -> tuple[Optional[slice], float, str]:
    # Prepare content lines, stripping whitespace and keeping track of original indices
    content_lines = [
        orig_content_lines[i].strip() for i in range(offset, len(orig_content_lines))
    ]
    new_to_original_indices = {}
    new_content_lines = []
    for i, line in enumerate(content_lines):
        if not line:
            continue
        new_content_lines.append(line)
        new_to_original_indices[len(new_content_lines) - 1] = i
    content_lines = new_content_lines

    # Prepare find lines, removing empty lines
    find_lines = [line.strip() for line in find_lines if line.strip()]

    # Initialize variables for best match tracking
    max_similarity = 0.0
    min_edit_distance_lines = None
    context_lines = []

    # For each possible starting position in content
    for i in range(max(1, len(content_lines) - len(find_lines) + 1)):
        # Calculate similarity for the block starting at position i
        block_similarity = 0.0
        for j in range(len(find_lines)):
            if (i + j) < len(content_lines):
                # Use SequenceMatcher for more efficient similarity calculation
                similarity = SequenceMatcher(
                    None, content_lines[i + j], find_lines[j]
                ).ratio()
                block_similarity += similarity

        # If this block is more similar than previous best
        if block_similarity > max_similarity:
            max_similarity = block_similarity
            # Map back to original line indices
            orig_start_index = new_to_original_indices[i]
            orig_end_index = (
                new_to_original_indices.get(
                    i + len(find_lines) - 1, len(orig_content_lines) - 1
                )
                + 1
            )
            # Get the original lines
            min_edit_distance_lines = slice(
                orig_start_index + offset, orig_end_index + offset
            )
            # Get context (10 lines before and after)
            context_lines = orig_content_lines[
                max(0, orig_start_index - 10 + offset) : (orig_end_index + 10 + offset)
            ]

    return (
        min_edit_distance_lines,
        max_similarity,
        "\n".join(context_lines),
    )
