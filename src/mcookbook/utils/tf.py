"""
Timeframe related utilities.
"""
from __future__ import annotations

from datetime import datetime
from datetime import timezone

import ccxt
from ccxt.base.decimal_to_precision import ROUND_DOWN  # pylint: disable=no-name-in-module
from ccxt.base.decimal_to_precision import ROUND_UP  # pylint: disable=no-name-in-module


def to_seconds(timeframe: str) -> int:
    """
    Translates the timeframe interval value written in the human readable.

    From ('1m', '5m', '1h', '1d', '1w', etc.) to the number of seconds for one timeframe interval.
    """
    seconds: int = ccxt.Exchange.parse_timeframe(timeframe)
    return seconds


def to_minutes(timeframe: str) -> int:
    """
    Same as to_seconds, but returns minutes.
    """
    return to_seconds(timeframe) // 60


def to_msecs(timeframe: str) -> int:
    """
    Same as to_seconds, but returns milliseconds.
    """
    return to_seconds(timeframe) * 1000


def to_prev_date(timeframe: str, date: datetime | None = None) -> datetime:
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


def to_next_date(timeframe: str, date: datetime | None = None) -> datetime:
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
