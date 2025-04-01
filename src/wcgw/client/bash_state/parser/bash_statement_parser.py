#!/usr/bin/env python3
"""
Bash Statement Parser

This script parses bash scripts and identifies individual statements using tree-sitter.
It correctly handles multi-line strings, command chains with && and ||, and semicolon-separated statements.
"""

import sys
from dataclasses import dataclass
from typing import Any, List, Optional

import tree_sitter_bash
from tree_sitter import Language, Parser


@dataclass
class Statement:
    """A bash statement with its source code and position information."""

    text: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    node_type: str
    parent_type: Optional[str] = None

    def __str__(self) -> str:
        return self.text.strip()


class BashStatementParser:
    def __init__(self) -> None:
        # Use the precompiled bash language
        self.language = Language(tree_sitter_bash.language())
        self.parser = Parser(self.language)

    def parse_file(self, file_path: str) -> List[Statement]:
        """Parse a bash script file and return a list of statements."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return self.parse_string(content)

    def parse_string(self, content: str) -> List[Statement]:
        """Parse a string containing bash script and return a list of statements."""
        tree = self.parser.parse(bytes(content, "utf-8"))
        root_node = tree.root_node

        # For debugging: Uncomment to print the tree structure
        # self._print_tree(root_node, content)

        statements: List[Statement] = []
        self._extract_statements(root_node, content, statements, None)

        # Post-process statements to handle multi-line statements correctly
        return self._post_process_statements(statements, content)

    def _print_tree(self, node: Any, content: str, indent: str = "") -> None:
        """Debug helper to print the entire syntax tree."""
        node_text = content[node.start_byte : node.end_byte]
        if len(node_text) > 40:
            node_text = node_text[:37] + "..."
        print(f"{indent}{node.type}: {repr(node_text)}")
        for child in node.children:
            self._print_tree(child, content, indent + "  ")

    def _extract_statements(
        self,
        node: Any,
        content: str,
        statements: List[Statement],
        parent_type: Optional[str],
    ) -> None:
        """Recursively extract statements from the syntax tree."""
        # Node types that represent bash statements
        statement_node_types = {
            # Basic statements
            "command",
            "variable_assignment",
            "declaration_command",
            "unset_command",
            # Control flow statements
            "for_statement",
            "c_style_for_statement",
            "while_statement",
            "if_statement",
            "case_statement",
            # Function definition
            "function_definition",
            # Command chains and groups
            "pipeline",  # For command chains with | and |&
            "list",  # For command chains with && and ||
            "compound_statement",
            "subshell",
            "redirected_statement",
        }

        # Create a Statement object for this node if it's a recognized statement type
        if node.type in statement_node_types:
            # Get the text of this statement
            start_byte = node.start_byte
            end_byte = node.end_byte
            statement_text = content[start_byte:end_byte]

            # Get line numbers
            start_line = (
                node.start_point[0] + 1
            )  # tree-sitter uses 0-indexed line numbers
            end_line = node.end_point[0] + 1

            statements.append(
                Statement(
                    text=statement_text,
                    start_line=start_line,
                    end_line=end_line,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    node_type=node.type,
                    parent_type=parent_type,
                )
            )

            # Update parent type for children
            parent_type = node.type

        # Recursively process all children
        for child in node.children:
            self._extract_statements(child, content, statements, parent_type)

    def _post_process_statements(
        self, statements: List[Statement], content: str
    ) -> List[Statement]:
        if not statements:
            return []

        # Filter out list statements that have been split
        top_statements = []
        for stmt in statements:
            # Skip statements that are contained within others
            is_contained = False
            for other in statements:
                if other is stmt:
                    continue

                # Check if completely contained (except for lists we've split)
                if other.node_type != "list" or ";" not in other.text:
                    if (
                        other.start_line <= stmt.start_line
                        and other.end_line >= stmt.end_line
                        and len(other.text) > len(stmt.text)
                        and stmt.text in other.text
                    ):
                        is_contained = True
                        break

            if not is_contained:
                top_statements.append(stmt)

        # Sort by position in file for consistent output
        top_statements.sort(key=lambda s: (s.start_line, s.text))

        return top_statements


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python bash_statement_parser.py <bash_script_file>")
        sys.exit(1)

    parser = BashStatementParser()
    statements = parser.parse_file(sys.argv[1])

    print(f"Found {len(statements)} statements:")
    for i, stmt in enumerate(statements, 1):
        print(f"\n--- Statement {i} (Lines {stmt.start_line}-{stmt.end_line}) ---")
        print(stmt)


if __name__ == "__main__":
    main()
