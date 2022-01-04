from __future__ import annotations

import copy
import re
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


def expand_pairlist(
    wildcardpl: list[str], available_pairs: list[str], keep_invalid: bool = False
) -> list[str]:
    """
    Expand pairlist potentially containing wildcards based on available markets.

    This will implicitly filter all pairs in the wildcard-list which are not in available_pairs.
    :param wildcardpl: List of Pairlists, which may contain regex
    :param available_pairs: List of all available pairs (`exchange.get_markets().keys()`)
    :param keep_invalid: If sets to True, drops invalid pairs silently while expanding regexes
    :return expanded pairlist, with Regexes from wildcardpl applied to match all available pairs.
    :raises: ValueError if a wildcard is invalid (like '*/BTC' - which should be `.*/BTC`)
    """
    result = []
    if keep_invalid:
        for pair_wc in wildcardpl:
            try:
                comp = re.compile(pair_wc, re.IGNORECASE)
                result_partial = [pair for pair in available_pairs if re.fullmatch(comp, pair)]
                # Add all matching pairs.
                # If there are no matching pairs (Pair not on exchange) keep it.
                result += result_partial or [pair_wc]
            except re.error as err:
                raise ValueError(f"Wildcard error in {pair_wc}, {err}")

        for element in result:
            if not re.fullmatch(r"^[A-Za-z0-9/-]+$", element):
                result.remove(element)
    else:
        for pair_wc in wildcardpl:
            try:
                comp = re.compile(pair_wc, re.IGNORECASE)
                result += [pair for pair in available_pairs if re.fullmatch(comp, pair)]
            except re.error as err:
                raise ValueError(f"Wildcard error in {pair_wc}, {err}")
    return result
