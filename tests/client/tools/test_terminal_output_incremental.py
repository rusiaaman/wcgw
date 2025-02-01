"""Tests for incremental terminal output handling"""
import unittest
from wcgw.client.tools import get_incremental_output

class TestIncrementalOutput(unittest.TestCase):
    def test_basic_incremental(self):
        """Test basic incremental output functionality"""
        # Test with no previous output
        old_output = []
        new_output = ["line1", "line2"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, new_output)
        
        # Test with matching sequence
        old_output = ["line1", "line2"]
        new_output = ["line1", "line2", "line3"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, ["line3"])
        
    def test_no_match_incremental(self):
        """Test incremental output with no matching sequence"""
        # Test with completely different content
        old_output = ["old1", "old2"]
        new_output = ["new1", "new2"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, new_output)
        
        # Test with empty new output
        old_output = ["old1"]
        new_output = []
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, [])
        
    def test_partial_match_incremental(self):
        """Test incremental output with partial matches"""
        # Test with partial match at start
        old_output = ["line1", "line2"]
        new_output = ["line1", "different", "line3"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, new_output)
        
        # Test with partial match at end
        old_output = ["line1", "line2"]
        new_output = ["different", "line2", "line3"]
        result = get_incremental_output(old_output, new_output)
        self.assertEqual(result, new_output)