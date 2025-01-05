"""Tests for diff_edit.py functionality."""

import unittest

from wcgw.client.file_ops.diff_edit import (
    FileEditOutput,
    Tolerance,
    TolerancesHit,
    find_least_edit_distance_substring,
    match_exact,
    match_with_tolerance,
    match_with_tolerance_empty_line,
    remove_leading_trailing_empty_lines,
)


class TestDiffEdit(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_file_edit_output_replace_or_throw(self):
        # Test successful replacement
        original_content = ["line1", "line2", "line3"]
        search_blocks = [["line2"]]
        replaced = [("line2-new",)]
        edited = [(slice(1, 2, 1), [], ["line2-new"])]

        output = FileEditOutput(
            original_content=original_content,
            orig_search_blocks=search_blocks,
            edited_with_tolerances=edited,
        )

        result, warnings = output.replace_or_throw(max_errors=1)
        self.assertEqual(result, ["line1", "line2-new", "line3"])
        self.assertEqual(warnings, set())

        # Test error cases
        tolerances_hit = TolerancesHit(
            line_process=lambda x: x,
            severity_cat="ERROR",
            score_multiplier=1.0,
            error_name="Test error",
            count=1,
        )
        edited_with_error = [(slice(1, 2, 1), [tolerances_hit], ["line2-new"])]
        output_with_error = FileEditOutput(
            original_content=original_content,
            orig_search_blocks=search_blocks,
            edited_with_tolerances=edited_with_error,
        )

        with self.assertRaises(Exception) as ctx:
            result, warnings = output_with_error.replace_or_throw(max_errors=1)
        self.assertIn("Test error", str(ctx.exception))

    def test_file_edit_output_get_best_match(self):
        # Create multiple outputs with different tolerance hits
        content = ["line1", "line2", "line3"]
        search_blocks = [["line2"]]
        edit1 = FileEditOutput(
            original_content=content,
            orig_search_blocks=search_blocks,
            edited_with_tolerances=[(slice(1, 2, 1), [], ["line2-new"])],
        )

        silent_tolerance = TolerancesHit(
            line_process=lambda x: x, severity_cat="SILENT", score_multiplier=1.0, error_name="", count=1
        )
        edit2 = FileEditOutput(
            original_content=content,
            orig_search_blocks=search_blocks,
            edited_with_tolerances=[
                (slice(1, 2, 1), [silent_tolerance], ["line2-new"])
            ],
        )

        warning_tolerance = TolerancesHit(
            line_process=lambda x: x,
            severity_cat="WARNING",
            score_multiplier=1.0,
            error_name="test warning",
            count=1,
        )
        edit3 = FileEditOutput(
            original_content=content,
            orig_search_blocks=search_blocks,
            edited_with_tolerances=[
                (slice(1, 2, 1), [warning_tolerance], ["line2-new"])
            ],
        )

        # Test preference order: ERROR < WARNING < SILENT
        best_matches, has_error = FileEditOutput.get_best_match([edit1, edit2, edit3])
        self.assertEqual(len(best_matches), 1)
        self.assertEqual(best_matches[0], edit1)
        self.assertFalse(has_error)

    def test_match_exact(self):
        # Test exact matches
        content = ["line1", "line2", "line3", "line2", "line4"]
        search = ["line2"]
        matches = match_exact(content, 0, search)
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0], slice(1, 2, 1))
        self.assertEqual(matches[1], slice(3, 4, 1))

        # Test no matches
        search = ["nonexistent"]
        matches = match_exact(content, 0, search)
        self.assertEqual(len(matches), 0)

        # Test empty inputs
        self.assertEqual(len(match_exact([], 0, search)), 0)
        self.assertEqual(len(match_exact(content, 0, [])), 0)

        # Test offset
        matches = match_exact(content, 2, ["line3"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0], slice(2, 3, 1))

    def test_match_with_tolerance(self):
        # Test with default tolerances
        content = ["  line1  ", "line2", " line3 "]
        search = ["line1"]
        matches = match_with_tolerance(
            content,
            0,
            search,
            [
                Tolerance(line_process=str.strip, severity_cat="SILENT", score_multiplier=1.0, error_name=""),
                Tolerance(line_process=str.lstrip, severity_cat="SILENT", score_multiplier=1.0, error_name=""),
                Tolerance(line_process=str.rstrip, severity_cat="SILENT", score_multiplier=1.0, error_name=""),
            ],
        )
        self.assertEqual(len(matches), 1)

        # Test multiple matches with different tolerances
        content = ["  line1", "line1  ", " line1 "]
        matches = match_with_tolerance(
            content,
            0,
            search,
            [
                Tolerance(line_process=str.strip, severity_cat="SILENT", score_multiplier=1.0, error_name=""),
                Tolerance(line_process=str.lstrip, severity_cat="SILENT", score_multiplier=1.0, error_name=""),
                Tolerance(line_process=str.rstrip, severity_cat="SILENT", score_multiplier=1.0, error_name=""),
            ],
        )
        self.assertEqual(len(matches), 3)

    def test_match_with_tolerance_empty_line(self):
        # Test with empty lines in content
        content = ["", "line1", "", "line2", "", ""]
        search = ["line1", "line2"]
        matches = match_with_tolerance_empty_line(
            content,
            0,
            search,
            [
                Tolerance(line_process=str.strip, severity_cat="SILENT", score_multiplier=1.0, error_name=""),
            ],
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], slice(1, 4, 1))

        # Test with empty lines in search
        content = ["line1", "line2"]
        search = ["", "line1", "", "line2", ""]
        matches = match_with_tolerance_empty_line(
            content,
            0,
            search,
            [
                Tolerance(line_process=str.strip, severity_cat="SILENT", score_multiplier=1.0, error_name=""),
            ],
        )
        self.assertEqual(len(matches), 1)

    def test_find_least_edit_distance_substring(self):
        # Test exact match
        content = ["line1", "line2", "line3"]
        find = ["line2"]
        match, sim, context = find_least_edit_distance_substring(content, 0, find)
        self.assertIsNotNone(match)
        self.assertTrue(sim > 0.9)  # High similarity for exact match

        # Test similar but not exact match
        content = ["line1", "lin2", "line3"]
        find = ["line2"]
        match, sim, context = find_least_edit_distance_substring(content, 0, find)
        self.assertIsNotNone(match)
        self.assertTrue(0.5 < sim < 1.0)  # Moderate similarity

        # Test no good match
        content = ["completely", "different", "content"]
        find = ["line2"]
        match, sim, context = find_least_edit_distance_substring(content, 0, find)
        self.assertTrue(sim < 0.5)  # Low similarity

    def test_remove_leading_trailing_empty_lines(self):
        # Test normal case
        lines = ["", "  ", "content", "more", "", "  "]
        result = remove_leading_trailing_empty_lines(lines)
        self.assertEqual(result, ["content", "more"])

        # Test no empty lines
        lines = ["content", "more"]
        result = remove_leading_trailing_empty_lines(lines)
        self.assertEqual(result, lines)

        # Test all empty lines
        lines = ["", "  ", "", "   "]
        result = remove_leading_trailing_empty_lines(lines)
        self.assertEqual(result, [])

        # Test empty input
        self.assertEqual(remove_leading_trailing_empty_lines([]), [])


if __name__ == "__main__":
    unittest.main()
