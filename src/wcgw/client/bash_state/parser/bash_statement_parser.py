#!/usr/bin/env python3
"""
Bash Statement Parser

This script parses bash scripts and identifies individual statements using tree-sitter.
It correctly handles multi-line strings, command chains with && and ||, and semicolon-separated statements.
"""

import sys
import os
import tree_sitter_bash
from tree_sitter import Language, Parser
from dataclasses import dataclass
from typing import List, Tuple, Set, Optional, Any

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
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return self.parse_string(content)
    
    def parse_string(self, content: str) -> List[Statement]:
        """Parse a string containing bash script and return a list of statements."""
        tree = self.parser.parse(bytes(content, 'utf-8'))
        root_node = tree.root_node
        
        # For debugging: Uncomment to print the tree structure
        # self._print_tree(root_node, content)
        
        statements: List[Statement] = []
        self._extract_statements(root_node, content, statements, None)
        
        # Post-process statements to handle multi-line statements correctly
        return self._post_process_statements(statements, content)
    
    def _print_tree(self, node: Any, content: str, indent: str = "") -> None:
        """Debug helper to print the entire syntax tree."""
        node_text = content[node.start_byte:node.end_byte]
        if len(node_text) > 40:
            node_text = node_text[:37] + "..."
        print(f"{indent}{node.type}: {repr(node_text)}")
        for child in node.children:
            self._print_tree(child, content, indent + "  ")
    
    def _extract_statements(self, node: Any, content: str, statements: List[Statement], parent_type: Optional[str]) -> None:
        """Recursively extract statements from the syntax tree."""
        # Node types that represent bash statements
        statement_node_types = {
            # Basic statements
            'command',
            'variable_assignment',
            'declaration_command',
            'unset_command',
            
            # Control flow statements
            'for_statement',
            'c_style_for_statement',
            'while_statement',
            'if_statement',
            'case_statement',
            
            # Function definition
            'function_definition',
            
            # Command chains and groups
            'pipeline',  # For command chains with | and |&
            'list',      # For command chains with && and ||
            'compound_statement',
            'subshell',
            'redirected_statement',
        }
        
        # Create a Statement object for this node if it's a recognized statement type
        if node.type in statement_node_types:
            # Get the text of this statement
            start_byte = node.start_byte
            end_byte = node.end_byte
            statement_text = content[start_byte:end_byte]
            
            # Get line numbers
            start_line = node.start_point[0] + 1  # tree-sitter uses 0-indexed line numbers
            end_line = node.end_point[0] + 1
            
            statements.append(Statement(
                text=statement_text,
                start_line=start_line,
                end_line=end_line,
                start_byte=start_byte,
                end_byte=end_byte,
                node_type=node.type,
                parent_type=parent_type
            ))
            
            # Update parent type for children
            parent_type = node.type
        
        # Special handling for semicolon-separated commands
        if node.type == 'program':
            # Process each direct child of the program node
            for i, child in enumerate(node.children):
                # Handle semicolon operators
                if child.type == ';' and i > 0 and i < len(node.children) - 1:
                    # The nodes before and after the semicolon are separate statements
                    prev_node = node.children[i-1]
                    next_node = node.children[i+1]
                    
                    # We'll handle these in the recursive calls below
                    pass
                
                self._extract_statements(child, content, statements, parent_type)
            return
            
        # Recursively process all children
        for child in node.children:
            self._extract_statements(child, content, statements, parent_type)
    
    def _post_process_statements(self, statements: List[Statement], content: str) -> List[Statement]:
        """
        Post-process statements to identify logical bash statements.
        
        We need to ensure that:
        1. Multi-line commands like echo "Yes\nOk" stay as one statement
        2. Commands connected by && or || stay as one statement
        3. Separate commands on separate lines are separate statements
        4. Semicolon-separated commands on the same line are separate statements
        """
        if not statements:
            return []
        
        # Find 'list' nodes, which may represent semicolon-separated commands
        # This is specifically for one-liners with semicolons
        semicolon_statements = []
        for stmt in statements:
            if stmt.node_type == 'list' and ';' in stmt.text and not stmt.text.strip().startswith('{'):
                # This is a list with semicolons - extract individual commands
                parts = self._split_semicolon_list(stmt.text, content, stmt.start_byte)
                if len(parts) > 1:
                    for part in parts:
                        if part.strip():
                            # Start/end lines are approximations
                            semicolon_statements.append(Statement(
                                text=part,
                                start_line=stmt.start_line,
                                end_line=stmt.end_line,
                                start_byte=0,  # These are not accurate for split statements
                                end_byte=0,
                                node_type='command',
                                parent_type='list'
                            ))
        
        # Add the semicolon-split statements to our list
        statements.extend(semicolon_statements)
        
        # Filter out list statements that have been split
        top_statements = []
        for stmt in statements:
            # Skip 'list' nodes that contain semicolons (we've already processed them)
            if stmt.node_type == 'list' and ';' in stmt.text and not stmt.text.strip().startswith('{'):
                continue
                
            # Skip statements that are contained within others
            is_contained = False
            for other in statements:
                if other is stmt:
                    continue
                
                # Check if completely contained (except for lists we've split)
                if (other.node_type != 'list' or ';' not in other.text):
                    if (other.start_line <= stmt.start_line and 
                        other.end_line >= stmt.end_line and
                        len(other.text) > len(stmt.text) and
                        stmt.text in other.text):
                        is_contained = True
                        break
            
            if not is_contained:
                top_statements.append(stmt)
        
        # Sort by position in file for consistent output
        top_statements.sort(key=lambda s: (s.start_line, s.text))
        
        # Remove duplicates by text content
        unique_statements = []
        seen_texts = set()
        for stmt in top_statements:
            clean_text = stmt.text.strip()
            if clean_text and clean_text not in seen_texts:
                seen_texts.add(clean_text)
                unique_statements.append(stmt)
        
        # Sort by line number for output
        unique_statements.sort(key=lambda s: s.start_line)
        return unique_statements
    
    def _split_semicolon_list(self, text: str, content: str, offset: int) -> List[str]:
        """Split a semicolon-separated list of commands into individual commands."""
        # This is a simplified approach that doesn't handle escaped semicolons or those in quotes
        # For a full implementation, we would need more sophisticated parsing
        
        # Simple case - just split by semicolons
        parts = []
        current_part = ""
        in_single_quote = False
        in_double_quote = False
        escaped = False
        
        for char in text:
            if escaped:
                current_part += char
                escaped = False
            elif char == '\\':
                current_part += char
                escaped = True
            elif char == "'" and not in_double_quote:
                current_part += char
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                current_part += char
                in_double_quote = not in_double_quote
            elif char == ';' and not in_single_quote and not in_double_quote:
                parts.append(current_part)
                current_part = ""
            else:
                current_part += char
                
        if current_part:
            parts.append(current_part)
            
        return parts

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
