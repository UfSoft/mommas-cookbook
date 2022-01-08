from __future__ import annotations

import logging

import polars as pl
from polars import DataFrame

from mcookbook.utils import timeframe_to_minutes

DEFAULT_DATAFRAME_COLUMNS = ["date", "open", "high", "low", "close", "volume"]

log = logging.getLogger(__name__)


def ohlcv_to_dataframe(
    ohlcv: list[tuple[int, float, float, float, float, float]],
    timeframe: str,
    pair: str,
    *,
    fill_missing: bool = True,
    drop_incomplete: bool = True,
) -> DataFrame:
    """
    Converts a list with candle (OHLCV) data (in format returned by ccxt.fetch_ohlcv)
    to a Dataframe
    :param ohlcv: list with candle (OHLCV) data, as returned by exchange.async_get_candle_history
    :param timeframe: timeframe (e.g. 5m). Used to fill up eventual missing data
    :param pair: Pair this data is for (used to warn if fillup was necessary)
    :param fill_missing: fill up missing candles with 0 candles
                         (see ohlcv_fill_up_missing_data for details)
    :param drop_incomplete: Drop the last candle of the dataframe, assuming it's incomplete
    :return: DataFrame
    """
    log.debug(f"Converting candle (OHLCV) data to dataframe for pair {pair}.")
    cols = DEFAULT_DATAFRAME_COLUMNS
    df = DataFrame(ohlcv, columns=cols)
    # Ensure proper types
    df_query = df.lazy().with_columns(
        [
            pl.col("date").cast(pl.Datetime),
            pl.col("open").cast(float),
            pl.col("high").cast(float),
            pl.col("low").cast(float),
            pl.col("close").cast(float),
            pl.col("volume").cast(float),
        ]
    )
    # group by date and aggregate results to eliminate duplicate ticks
    df_query.groupby(by="date").agg(
        [
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").max().alias("volume"),
        ]
    ).sort("date")
    if drop_incomplete:
        df_query = df_query.slice(0, df.shape[0] - 1)
    if fill_missing:
        df = df_query.collect()
        bounds = df.select([pl.col("date").min().alias("low"), pl.col("date").max().alias("high")])
        high = bounds["high"].dt[0]
        low = bounds["low"].dt[0]
        upsampled = pl.date_range(
            low, high, f"{timeframe_to_minutes(timeframe)}m", name="date", time_unit="ms"
        )
        # Merge the resampled dataframe, with the original dataframe
        df = pl.DataFrame(upsampled).join(df, on="date", how="left")
        df.join(
            df.select([pl.col("date"), pl.col("close")]).fill_null("forward"),
            on="date",
            how="left",  # Fill missing data
        ).with_column(
            # Rename the close_right column from the merge
            pl.col("close_right").alias("close")
            # Drop the close_right column now that we have the merged data in close
        ).drop(
            "close_right"
        ).with_columns(
            [
                # Fill missing open/high/low with the value of close
                pl.col("open").fill_null(pl.col("close")),
                pl.col("high").fill_null(pl.col("close")),
                pl.col("low").fill_null(pl.col("close")),
                # Fill missing volume with 0.0
                pl.col("volume").fill_null(0.0),
            ]
        )
        return df
    return df_query.collect()
