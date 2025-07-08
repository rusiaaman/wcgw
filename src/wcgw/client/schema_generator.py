"""
Custom JSON schema generator to remove title fields from Pydantic models.

This module provides utilities to remove auto-generated title fields from JSON schemas,
making them more suitable for tool schemas where titles are not needed.
"""

import copy
from typing import Any, Dict


def recursive_purge_dict_key(d: Dict[str, Any], k: str) -> None:
    """
    Remove a key from a dictionary recursively, but only from JSON schema metadata.
    
    This function removes the specified key from dictionaries that appear to be
    JSON schema objects (have "type" or "$ref" or are property definitions).
    This prevents removing legitimate data fields that happen to have the same name.
    
    Args:
        d: The dictionary to clean
        k: The key to remove (typically "title")
    """
    if isinstance(d, dict):
        # Only remove the key if this looks like a JSON schema object
        # This includes objects with "type", "$ref", or if we're in a "properties" context
        is_schema_object = (
            "type" in d or 
            "$ref" in d or 
            any(schema_key in d for schema_key in ["properties", "items", "additionalProperties", "enum", "const", "anyOf", "allOf", "oneOf"])
        )
        
        if is_schema_object and k in d:
            del d[k]
        
        # Recursively process all values, regardless of key names
        # This ensures we catch all nested structures
        for key, value in d.items():
            if isinstance(value, dict):
                recursive_purge_dict_key(value, k)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        recursive_purge_dict_key(item, k)


def remove_titles_from_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove all 'title' keys from a JSON schema dictionary.

    This function creates a copy of the schema and removes all title keys
    recursively, making it suitable for use with APIs that don't need titles.

    Args:
        schema: The JSON schema dictionary to clean

    Returns:
        A new dictionary with all title keys removed
    """

    schema_copy = copy.deepcopy(schema)
    recursive_purge_dict_key(schema_copy, "title")
    return schema_copy
