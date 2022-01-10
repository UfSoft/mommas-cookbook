"""
Data related utilities.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime
from datetime import timezone
from typing import Any

from pandas import DataFrame
from pandas import to_datetime

from mcookbook.utils import tf

DEFAULT_DATAFRAME_COLUMNS = ["date", "open", "high", "low", "close", "volume"]

log = logging.getLogger(__name__)


def ohlcv_to_dataframe(
    ohlcv: list[dict[str, Any]],
    timeframe: str,
    pair: str,
    *,
    fill_missing: bool = True,
    drop_incomplete: bool = True,
) -> DataFrame:
    """
    Converts a list with candle (OHLCV) data (in format returned by ccxt.fetch_ohlcv) to a Dataframe.

    :param ohlcv: list with candle (OHLCV) data, as returned by exchange.async_get_candle_history
    :param timeframe: timeframe (e.g. 5m). Used to fill up eventual missing data
    :param pair: Pair this data is for (used to warn if fillup was necessary)
    :param fill_missing: fill up missing candles with 0 candles
                         (see ohlcv_fill_up_missing_data for details)
    :param drop_incomplete: Drop the last candle of the dataframe, assuming it's incomplete
    :return: DataFrame
    """
    log.debug("Converting candle (OHLCV) data to dataframe for pair %s", pair)
    cols = DEFAULT_DATAFRAME_COLUMNS
    df = DataFrame(ohlcv, columns=cols)

    df["date"] = to_datetime(df["date"], unit="ms", utc=True, infer_datetime_format=True)

    # Some exchanges return int values for Volume and even for OHLC.
    # Convert them since TA-LIB indicators used in the strategy assume floats
    # and fail with exception...
    df = df.astype(
        dtype={
            "open": "float",
            "high": "float",
            "low": "float",
            "close": "float",
            "volume": "float",
        }
    )
    return clean_ohlcv_dataframe(
        df, timeframe, pair, fill_missing=fill_missing, drop_incomplete=drop_incomplete
    )


def clean_ohlcv_dataframe(
    data: DataFrame,
    timeframe: str,
    pair: str,
    *,
    fill_missing: bool = True,
    drop_incomplete: bool = True,
) -> DataFrame:
    """
    Cleanse a OHLCV dataframe.

    By:
      * Grouping it by date (removes duplicate tics)
      * dropping last candles if requested
      * Filling up missing data (if requested)
    :param data: DataFrame containing candle (OHLCV) data.
    :param timeframe: timeframe (e.g. 5m). Used to fill up eventual missing data
    :param pair: Pair this data is for (used to warn if fillup was necessary)
    :param fill_missing: fill up missing candles with 0 candles
                         (see ohlcv_fill_up_missing_data for details)
    :param drop_incomplete: Drop the last candle of the dataframe, assuming it's incomplete
    :return: DataFrame
    """
    # group by index and aggregate results to eliminate duplicate ticks
    data = data.groupby(by="date", as_index=False, sort=True).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "max",
        }
    )
    # eliminate partial candle
    if drop_incomplete:
        data.drop(data.tail(1).index, inplace=True)
        log.debug("Dropping last candle")

    if fill_missing:
        return ohlcv_fill_up_missing_data(data, timeframe, pair)
    else:
        return data


def ohlcv_fill_up_missing_data(dataframe: DataFrame, timeframe: str, pair: str) -> DataFrame:
    """
    Fill missing dataframe data.

    Fills up missing data with 0 volume rows,
    using the previous close as price for "open", "high" "low" and "close", volume is set to 0

    """
    ohlcv_dict = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    timeframe_minutes = tf.to_minutes(timeframe)
    # Resample to create "NAN" values
    df = dataframe.resample(f"{timeframe_minutes}min", on="date").agg(ohlcv_dict)

    # Forward fill close for missing columns
    df["close"] = df["close"].fillna(method="ffill")
    # Use close for "open, high, low"
    df.loc[:, ["open", "high", "low"]] = df[["open", "high", "low"]].fillna(
        value={
            "open": df["close"],
            "high": df["close"],
            "low": df["close"],
        }
    )
    df.reset_index(inplace=True)
    len_before = len(dataframe)
    len_after = len(df)
    pct_missing = (len_after - len_before) / len_before if len_before > 0 else 0
    if len_before != len_after:
        message = (
            f"Missing data fill-up for {pair}: before: {len_before} - after: {len_after}"
            f" - {pct_missing:.2%}"
        )
        if pct_missing > 0.01:
            log.info(message)
        else:
            # Don't be verbose if only a small amount is missing
            log.debug(message)
    return df


def trim_dataframe(
    df: DataFrame, timerange: Any, df_date_col: str = "date", startup_candles: int = 0
) -> DataFrame:
    """
    Trim dataframe based on given timerange.

    :param df: Dataframe to trim
    :param timerange: timerange (use start and end date if available)
    :param df_date_col: Column in the dataframe to use as Date column
    :param startup_candles: When not 0, is used instead the timerange start date
    :return: trimmed dataframe
    """
    if startup_candles:
        # Trim candles instead of timeframe in case of given startup_candle count
        df = df.iloc[startup_candles:, :]
    else:
        if timerange.starttype == "date":
            start = datetime.fromtimestamp(timerange.startts, tz=timezone.utc)
            df = df.loc[df[df_date_col] >= start, :]
    if timerange.stoptype == "date":
        stop = datetime.fromtimestamp(timerange.stopts, tz=timezone.utc)
        df = df.loc[df[df_date_col] <= stop, :]
    return df


def chunks(_list: list[Any], size: int) -> Iterator[list[Any]]:
    """
    Split _list into chunks of the size `size`.

    :param _list: list to split into chunks
    :param size: number of max elements per chunk
    :return: None
    """
    for chunk in range(0, len(_list), size):
        yield _list[chunk : chunk + size]  # noqa: E203
