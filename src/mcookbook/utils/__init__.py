from __future__ import annotations

import copy
import re
from collections.abc import Iterator
from datetime import datetime
from datetime import timezone
from typing import Any

import ccxt
from ccxt.base.decimal_to_precision import decimal_to_precision
from ccxt.base.decimal_to_precision import ROUND_DOWN
from ccxt.base.decimal_to_precision import ROUND_UP
from ccxt.base.decimal_to_precision import TICK_SIZE
from ccxt.base.decimal_to_precision import TRUNCATE


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
                raise ValueError(f"Wildcard error in {pair_wc}, {err}") from err

        for element in result:
            if not re.fullmatch(r"^[A-Za-z0-9/-]+$", element):
                result.remove(element)
    else:
        for pair_wc in wildcardpl:
            try:
                comp = re.compile(pair_wc, re.IGNORECASE)
                result += [pair for pair in available_pairs if re.fullmatch(comp, pair)]
            except re.error as err:
                raise ValueError(f"Wildcard error in {pair_wc}, {err}") from err
    return result


def timeframe_to_seconds(timeframe: str) -> int:
    """
    Translates the timeframe interval value written in the human readable.

    From ('1m', '5m', '1h', '1d', '1w', etc.) to the number of seconds for one timeframe interval.
    """
    seconds: int = ccxt.Exchange.parse_timeframe(timeframe)
    return seconds


def timeframe_to_minutes(timeframe: str) -> int:
    """
    Same as timeframe_to_seconds, but returns minutes.
    """
    return timeframe_to_seconds(timeframe) // 60


def timeframe_to_msecs(timeframe: str) -> int:
    """
    Same as timeframe_to_seconds, but returns milliseconds.
    """
    return timeframe_to_seconds(timeframe) * 1000


def timeframe_to_prev_date(timeframe: str, date: datetime | None = None) -> datetime:
    """
    Use Timeframe and determine last possible candle.
    :param timeframe: timeframe in string format (e.g. "5m")
    :param date: date to use. Defaults to utcnow()
    :returns: date of previous candle (with utc timezone)
    """
    if not date:
        date = datetime.now(timezone.utc)

    new_timestamp = (
        ccxt.Exchange.round_timeframe(timeframe, date.timestamp() * 1000, ROUND_DOWN) // 1000
    )
    return datetime.fromtimestamp(new_timestamp, tz=timezone.utc)


def timeframe_to_next_date(timeframe: str, date: datetime | None = None) -> datetime:
    """
    Use Timeframe and determine next candle.
    :param timeframe: timeframe in string format (e.g. "5m")
    :param date: date to use. Defaults to utcnow()
    :returns: date of next candle (with utc timezone)
    """
    if not date:
        date = datetime.now(timezone.utc)
    new_timestamp = (
        ccxt.Exchange.round_timeframe(timeframe, date.timestamp() * 1000, ROUND_UP) // 1000
    )
    return datetime.fromtimestamp(new_timestamp, tz=timezone.utc)


def format_ms_time(date: int) -> str:
    """
    Convert MS date to readable format.
    """
    return datetime.fromtimestamp(date / 1000.0).strftime("%Y-%m-%dT%H:%M:%S")


def chunks(lst: list[Any], n: int) -> Iterator[list[Any]]:
    """
    Split lst into chunks of the size n.
    :param lst: list to split into chunks
    :param n: number of max elements per chunk
    :return: None
    """
    for chunk in range(0, len(lst), n):
        yield (lst[chunk : chunk + n])
