import pytest
from wcgw.client.tools import _is_int

def test_is_int_validation():
    """Test _is_int function with various inputs"""
    # Valid integers
    assert _is_int("123") is True
    assert _is_int("-123") is True
    assert _is_int("0") is True
    assert _is_int("０１２３") is True  # Full-width numbers are actually valid
    
    # Invalid cases
    assert _is_int("123abc") is False  # Mixed content
    assert _is_int("12.3") is False    # Decimal
    assert _is_int("") is False        # Empty string
    assert _is_int("①②③") is False     # Circle numbers

def test_is_int_edge_cases():
    """Test edge cases for _is_int function"""
    assert _is_int("+123") is True     # Positive sign
    assert _is_int("-0") is True       # Negative zero
    assert _is_int("00123") is True    # Leading zeros
    assert _is_int(" 123") is True     # Leading space
    assert _is_int("123 ") is True     # Trailing space
    assert _is_int(" 123 ") is True    # Both spaces