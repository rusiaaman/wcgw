"""
Tests for the bash statement parser.
"""

import pytest
from unittest.mock import patch

from wcgw.client.bash_state.parser.bash_statement_parser import BashStatementParser


def test_bash_statement_parser_basic():
    """Test basic statement parsing."""
    parser = BashStatementParser()
    
    # Test single statement
    statements = parser.parse_string("echo hello")
    assert len(statements) == 1
    assert statements[0].text == "echo hello"
    
    # Test command with newlines inside string
    statements = parser.parse_string('echo "hello\nworld"')
    assert len(statements) == 1
    
    # Test command with && chain
    statements = parser.parse_string("echo hello && echo world")
    assert len(statements) == 1
    
    # Test command with || chain
    statements = parser.parse_string("echo hello || echo world")
    assert len(statements) == 1
    
    # Test command with pipe
    statements = parser.parse_string("echo hello | grep hello")
    assert len(statements) == 1


def test_bash_statement_parser_multiple():
    """Test multiple statement detection."""
    parser = BashStatementParser()
    
    # Test multiple statements on separate lines
    statements = parser.parse_string("echo hello\necho world")
    assert len(statements) == 2
    
    # Test multiple statements with semicolons
    statements = parser.parse_string("echo hello; echo world")
    assert len(statements) == 2
    
    # Test more complex case
    statements = parser.parse_string("echo hello; echo world && echo again")
    assert len(statements) == 2
    
    # Test mixed separation
    statements = parser.parse_string("echo a; echo b\necho c")
    assert len(statements) == 3


def test_bash_statement_parser_complex():
    """Test complex statement handling."""
    parser = BashStatementParser()
    
    # Test subshell
    statements = parser.parse_string("(echo hello; echo world)")
    assert len(statements) == 1
    
    # Test braces
    statements = parser.parse_string("{ echo hello; echo world; }")
    assert len(statements) == 1
    
    # Test semicolons in strings
    statements = parser.parse_string('echo "hello;world"')
    assert len(statements) == 1
    
    # Test escaped semicolons
    statements = parser.parse_string('echo hello\\; echo world')
    assert len(statements) == 1
    
    # Test quoted semicolons
    statements = parser.parse_string("echo 'hello;world'")
    assert len(statements) == 1
