from __future__ import annotations

from typing import Any


def merge_dictionaries(target_dict: dict[Any, Any], *source_dicts: dict[Any, Any]) -> None:
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
