"""
File with definitions of known source code file extensions.
Used to determine the appropriate context length for files.
Supports selecting between coding_max_tokens and noncoding_max_tokens
based on file extensions.
"""
from typing import Dict, Optional, Set

# Set of file extensions considered to be source code
# Each extension should be listed without the dot (e.g., 'py' not '.py')
SOURCE_CODE_EXTENSIONS: Set[str] = {
    # Python
    'py', 'pyx', 'pyi', 'pyw',
    
    # JavaScript and TypeScript
    'js', 'jsx', 'ts', 'tsx', 'mjs', 'cjs',
    
    # Web
    'html', 'htm', 'xhtml', 'css', 'scss', 'sass', 'less',
    
    # C and C++
    'c', 'h', 'cpp', 'cxx', 'cc', 'hpp', 'hxx', 'hh', 'inl',
    
    # C#
    'cs', 'csx',
    
    # Java
    'java', 'scala', 'kt', 'kts', 'groovy',
    
    # Go
    'go', 'mod',
    
    # Rust
    'rs', 'rlib',
    
    # Swift
    'swift',
    
    # Ruby
    'rb', 'rake', 'gemspec',
    
    # PHP
    'php', 'phtml', 'phar', 'phps',
    
    # Shell
    'sh', 'bash', 'zsh', 'fish',
    
    # PowerShell
    'ps1', 'psm1', 'psd1',
    
    # SQL
    'sql', 'ddl', 'dml',
    
    # Markup and config
    'xml', 'json', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'conf',
    
    # Documentation
    'md', 'markdown', 'rst', 'adoc', 'tex',
    
    # Build and dependency files
    'Makefile', 'Dockerfile', 'Jenkinsfile',
    
    # Haskell
    'hs', 'lhs',
    
    # Lisp family
    'lisp', 'cl', 'el', 'clj', 'cljs', 'edn', 'scm',
    
    # Erlang and Elixir
    'erl', 'hrl', 'ex', 'exs',
    
    # Dart and Flutter
    'dart',
    
    # Objective-C
    'm', 'mm',
}

# Context length limits based on file type (in tokens)
CONTEXT_LENGTH_LIMITS: Dict[str, int] = {
    'source_code': 24000,  # For known source code files
    'default': 8000,       # For all other files
}

def is_source_code_file(filename: str) -> bool:
    """
    Determine if a file is a source code file based on its extension.
    
    Args:
        filename: The name of the file to check
        
    Returns:
        True if the file has a recognized source code extension, False otherwise
    """
    # Extract extension (without the dot)
    parts = filename.split('.')
    if len(parts) > 1:
        ext = parts[-1].lower()
        return ext in SOURCE_CODE_EXTENSIONS
    
    # Files without extensions (like 'Makefile', 'Dockerfile')
    # Case-insensitive match for files without extensions
    return filename.lower() in {ext.lower() for ext in SOURCE_CODE_EXTENSIONS}

def get_context_length_for_file(filename: str) -> int:
    """
    Get the appropriate context length limit for a file based on its extension.
    
    Args:
        filename: The name of the file to check
        
    Returns:
        The context length limit in tokens
    """
    if is_source_code_file(filename):
        return CONTEXT_LENGTH_LIMITS['source_code']
    return CONTEXT_LENGTH_LIMITS['default']


def select_max_tokens(filename: str, coding_max_tokens: Optional[int], noncoding_max_tokens: Optional[int]) -> Optional[int]:
    """
    Select the appropriate max_tokens limit based on file type.
    
    Args:
        filename: The name of the file to check
        coding_max_tokens: Maximum tokens for source code files
        noncoding_max_tokens: Maximum tokens for non-source code files
        
    Returns:
        The appropriate max_tokens limit for the file
    """
    if coding_max_tokens is None and noncoding_max_tokens is None:
        return None
        
    if is_source_code_file(filename):
        return coding_max_tokens
    return noncoding_max_tokens
