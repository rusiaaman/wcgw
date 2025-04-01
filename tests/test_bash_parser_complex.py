"""
Tests specifically for complex bash parsing scenarios.
"""

from wcgw.client.bash_state.parser.bash_statement_parser import BashStatementParser


def test_semicolon_lists():
    """Test parsing of semicolon-separated commands."""
    parser = BashStatementParser()

    # Simple case: two commands separated by semicolon
    statements = parser.parse_string("echo a; echo b")
    assert len(statements) == 2
    assert statements[0].text.strip() == "echo a"
    assert statements[1].text.strip() == "echo b"

    # Multiple semicolons
    statements = parser.parse_string("echo a; echo b; echo c")
    assert len(statements) == 3
    assert statements[0].text.strip() == "echo a"
    assert statements[1].text.strip() == "echo b"
    assert statements[2].text.strip() == "echo c"

    # Semicolons with whitespace
    statements = parser.parse_string("echo a  ;  echo b")
    assert len(statements) == 2
    assert statements[0].text.strip() == "echo a"
    assert statements[1].text.strip() == "echo b"


def test_bash_command_with_semicolons_in_quotes():
    """Test that semicolons inside quotes don't split statements."""
    parser = BashStatementParser()

    # Semicolon in single quotes
    statements = parser.parse_string("echo 'a;b'")
    assert len(statements) == 1

    # Semicolon in double quotes
    statements = parser.parse_string('echo "a;b"')
    assert len(statements) == 1

    # Mixed quotes
    statements = parser.parse_string("echo \"a;b\" ; echo 'c;d'")
    assert len(statements) == 2


def test_complex_commands():
    """Test complex command scenarios."""
    parser = BashStatementParser()

    # Command with redirection and semicolon
    statements = parser.parse_string("cat > file.txt << EOF\ntest\nEOF\n; echo done")
    assert len(statements) == 2

    # Command with subshell and semicolon
    statements = parser.parse_string("(cd /tmp && echo 'in tmp'); echo 'outside'")
    assert len(statements) == 2

    # Command with braces and semicolon
    statements = parser.parse_string("{ echo a; echo b; }; echo c")
    assert len(statements) == 2


def test_command_chaining():
    """Test command chains are treated as a single statement."""
    parser = BashStatementParser()

    # AND chaining
    statements = parser.parse_string("echo a && echo b")
    assert len(statements) == 1

    # OR chaining
    statements = parser.parse_string("echo a || echo b")
    assert len(statements) == 1

    # Pipe chaining
    statements = parser.parse_string("echo a | grep a")
    assert len(statements) == 1

    # Mixed chaining
    statements = parser.parse_string("echo a && echo b || echo c")
    assert len(statements) == 1
