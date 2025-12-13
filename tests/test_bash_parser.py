"""
Tests for the bash statement parser.
"""

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


def test_comments():
    """Test comment handling."""
    parser = BashStatementParser()

    # Test comment followed by command
    statements = parser.parse_string("# Test\nls")
    assert len(statements) == 2
    assert statements[0].text == "# Test"
    assert statements[0].node_type == "comment"
    assert statements[1].text == "ls"

    # Test multiple comments
    statements = parser.parse_string("# Comment 1\n# Comment 2\necho hello")
    assert len(statements) == 3
    assert statements[0].node_type == "comment"
    assert statements[1].node_type == "comment"
    assert statements[2].node_type == "command"

    # Test inline comment (parsed as separate statement after command)
    statements = parser.parse_string("echo hello # inline comment")
    assert len(statements) == 2
    assert statements[0].text == "echo hello"
    assert statements[0].node_type == "command"
    assert statements[1].text == "# inline comment"
    assert statements[1].node_type == "comment"

    # Test comment with semicolon
    statements = parser.parse_string("# Comment\necho a; echo b")
    assert len(statements) == 3
    assert statements[0].node_type == "comment"

    # Test only comment
    statements = parser.parse_string("# Just a comment")
    assert len(statements) == 1
    assert statements[0].node_type == "comment"

    # Test empty lines with comments
    statements = parser.parse_string("# Comment 1\n\n# Comment 2\n\nls")
    assert len(statements) == 3
    assert statements[0].node_type == "comment"
    assert statements[1].node_type == "comment"
    assert statements[2].node_type == "command"


def test_complete_control_structures():
    """Test that complete control structures are treated as single statements."""
    parser = BashStatementParser()

    # Test if statement (complete - should be 1 statement)
    statements = parser.parse_string("if [ -f file ]; then\n  echo found\nfi")
    assert len(statements) == 1
    assert statements[0].node_type == "if_statement"

    # Test for loop (complete - should be 1 statement)
    statements = parser.parse_string("for i in 1 2 3; do\n  echo $i\ndone")
    assert len(statements) == 1
    assert statements[0].node_type == "for_statement"

    # Test while loop (complete - should be 1 statement)
    statements = parser.parse_string("while true; do\n  echo loop\n  break\ndone")
    assert len(statements) == 1
    assert statements[0].node_type == "while_statement"

    # Test case statement (complete - should be 1 statement)
    statements = parser.parse_string(
        'case $var in\n  a) echo A ;;\n  b) echo B ;;\nesac'
    )
    assert len(statements) == 1
    assert statements[0].node_type == "case_statement"

    # Test function definition (complete - should be 1 statement)
    statements = parser.parse_string("function myfunc() {\n  echo hello\n}")
    assert len(statements) == 1
    assert statements[0].node_type == "function_definition"


def test_multiline_strings():
    """Test that multi-line strings in quotes are treated as single statements."""
    parser = BashStatementParser()

    # Test double-quoted multi-line string (complete - should be 1 statement)
    statements = parser.parse_string('echo "line 1\nline 2\nline 3"')
    assert len(statements) == 1
    assert statements[0].node_type == "command"

    # Test single-quoted multi-line string (complete - should be 1 statement)
    statements = parser.parse_string("echo 'line 1\nline 2\nline 3'")
    assert len(statements) == 1
    assert statements[0].node_type == "command"


def test_line_continuation():
    """Test that line continuations with backslash are treated as single statements."""
    parser = BashStatementParser()

    # Test backslash continuation (complete - should be 1 statement)
    statements = parser.parse_string("echo hello \\\n  world \\\n  again")
    assert len(statements) == 1
    assert statements[0].node_type == "command"

    # Test multiple commands with continuation
    statements = parser.parse_string("echo a \\\n  b\necho c")
    assert len(statements) == 2


def test_here_documents():
    """Test that here documents are treated as single statements."""
    parser = BashStatementParser()

    # Test here document (complete - should be 1 statement)
    statements = parser.parse_string("cat <<EOF\nline 1\nline 2\nEOF")
    assert len(statements) == 1
    assert statements[0].node_type == "redirected_statement"

    # Test here document with command after
    statements = parser.parse_string("cat <<EOF\ndata\nEOF\necho done")
    assert len(statements) == 2


def test_subshells_and_command_substitution():
    """Test subshells and command substitution."""
    parser = BashStatementParser()

    # Test subshell (complete - should be 1 statement)
    statements = parser.parse_string("(cd /tmp && ls)")
    assert len(statements) == 1
    assert statements[0].node_type == "subshell"

    # Test command substitution in assignment
    statements = parser.parse_string("result=$(echo hello)")
    assert len(statements) == 1
    assert statements[0].node_type == "variable_assignment"

    # Test nested subshells
    statements = parser.parse_string("echo $(echo $(echo nested))")
    assert len(statements) == 1
    assert statements[0].node_type == "command"


def test_compound_statements():
    """Test compound statements with braces."""
    parser = BashStatementParser()

    # Test brace group (complete - should be 1 statement)
    statements = parser.parse_string("{ echo a; echo b; }")
    assert len(statements) == 1
    assert statements[0].node_type == "compound_statement"

    # Test brace group with newlines
    statements = parser.parse_string("{\n  echo a\n  echo b\n}")
    assert len(statements) == 1
    assert statements[0].node_type == "compound_statement"


def test_complex_pipelines():
    """Test complex pipelines and command chains."""
    parser = BashStatementParser()

    # Test multi-line pipeline (complete - should be 1 statement)
    statements = parser.parse_string("cat file | \\\n  grep pattern | \\\n  sort")
    assert len(statements) == 1
    assert statements[0].node_type == "pipeline"

    # Test command chain with && and || (complete - should be 1 statement)
    statements = parser.parse_string("cmd1 && \\\n  cmd2 || \\\n  cmd3")
    assert len(statements) == 1
    assert statements[0].node_type == "list"


def test_mixed_complete_statements():
    """Test mixing different types of complete statements."""
    parser = BashStatementParser()

    # Test function followed by call
    statements = parser.parse_string(
        "myfunc() {\n  echo hello\n}\nmyfunc\necho done"
    )
    assert len(statements) == 3
    assert statements[0].node_type == "function_definition"
    assert statements[1].node_type == "command"
    assert statements[2].node_type == "command"

    # Test if statement followed by command
    statements = parser.parse_string("if true; then\n  echo yes\nfi\necho after")
    assert len(statements) == 2
    assert statements[0].node_type == "if_statement"
    assert statements[1].node_type == "command"

    # Test comment, command, and control structure
    statements = parser.parse_string(
        "# Setup\nexport VAR=value\nfor i in 1 2; do\n  echo $i\ndone"
    )
    assert len(statements) == 3
    assert statements[0].node_type == "comment"
    assert statements[1].node_type == "declaration_command"
    assert statements[2].node_type == "for_statement"
