"""
Python dictionaries related utilities.
"""
from __future__ import annotations

import copy
from typing import Any


def merge_dictionaries(
    target_dict: dict[Any, Any], *source_dicts: dict[Any, Any]
) -> dict[Any, Any]:
    """
    Recursively merge each of the ``source_dicts`` into ``target_dict`` in-place.
    """
    for source_dict in source_dicts:
        for key, value in source_dict.items():
            if isinstance(value, dict):
                target_dict_value = target_dict.setdefault(key, {})
                merge_dictionaries(target_dict_value, value)
            else:
                target_dict[key] = value
    return target_dict


def sanitize_dictionary(
    target_dict: dict[str, Any], keys: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    """
    Sanitize a dictionary by obfuscating the values of the passed keys.
    """
    return_dict = copy.deepcopy(target_dict)
    for key, value in return_dict.items():
        if isinstance(value, dict):
            return_dict[key] = sanitize_dictionary(return_dict[key], keys)
            continue
        if key in keys:
            return_dict[key] = "******"
    return return_dict
