"""
Base exchange class implementation.
"""
# pylint: disable=no-member,not-an-iterable,unsubscriptable-object
from __future__ import annotations

import abc
import asyncio
import gc
import logging
import operator
from datetime import timedelta
from typing import Any
from typing import TYPE_CHECKING

import arrow
import attrs
import ccxt
from pandas import DataFrame

import mcookbook.utils.tf as tf
from mcookbook.config.trade import TradeConfig
from mcookbook.events import Events
from mcookbook.exceptions import DDosProtection
from mcookbook.exceptions import OperationalException
from mcookbook.exceptions import TemporaryError
from mcookbook.utils.ccxt import CCXTExchange
from mcookbook.utils.data import chunks
from mcookbook.utils.data import ohlcv_to_dataframe
from mcookbook.utils.dicts import merge_dictionaries
from mcookbook.utils.retry import async_retrier

log = logging.getLogger(__name__)

PairWithTimeframe = tuple[str, str]
ListPairsWithTimeframes = list[PairWithTimeframe]


if TYPE_CHECKING:
    from mcookbook.config.base import BaseConfig


@attrs.define(kw_only=True)
class Exchange(abc.ABC):
    """
    Base Exchange class.
    """

    name: str = attrs.field(default=None)
    market: str = attrs.field(default=None)

    config: TradeConfig = attrs.field()
    events: Events = attrs.field()
    ccxt_conn: CCXTExchange = attrs.field()

    _exchange_supports: dict[str, Any] = attrs.field(init=False, repr=False, factory=dict)
    _exchange_supports_defaults: dict[str, Any] = attrs.field(init=False, repr=False)
    exchange_supports: dict[str, Any] = attrs.field(init=False, repr=False)

    _markets: dict[str, dict[str, Any]] = attrs.field(init=False, repr=False, factory=dict)
    _klines: dict[tuple[str, str], DataFrame] = attrs.field(init=False, factory=dict)
    _pairs_last_refresh_time: dict[tuple[str, str], int] = attrs.field(init=False, factory=dict)

    @_exchange_supports_defaults.default  # type: ignore[attr-defined,misc]
    def _set_exchange_supports_defaults(self) -> dict[str, Any]:
        # Dict to specify which options each exchange implements
        # This defines defaults, which can be selectively overridden by subclasses using _ft_has
        # or by specifying them in the configuration.
        return {
            "stoploss_on_exchange": False,
            "order_time_in_force": ["gtc"],
            "time_in_force_parameter": "timeInForce",
            "ohlcv_params": {},
            "ohlcv_candle_limit": 500,
            "ohlcv_partial_candle": True,
            "trades_pagination": "time",  # Possible are "time" or "id"
            "trades_pagination_arg": "since",
            "l2_limit_range": None,
            "l2_limit_range_required": True,  # Allow Empty L2 limit (kucoin)
        }

    @exchange_supports.default  # type: ignore[attr-defined,misc]
    def _build_exchange_supports(self) -> dict[str, Any]:
        return merge_dictionaries({}, self._exchange_supports_defaults, self._exchange_supports)

    def __attrs_post_init__(self) -> None:
        """
        Post attrs, initialization routines.
        """
        self.events.on_start.register(self._on_start)
        self.events.on_pairs_available.register(self._on_pairs_available)

    async def _on_start(self) -> None:
        await self.get_markets()

    async def _on_pairs_available(self, pairs: list[str]) -> None:
        # Since 61 days ago, starting at midnight
        how_many_days = 1
        log.info("Loading %d days worth of 1m candles for pairs: %s", how_many_days, pairs)
        since_ms = arrow.utcnow().floor("days").shift(days=-how_many_days).int_timestamp * 1000
        timeframes = ["1m", "15m", "1h", "1d"]
        timeframes = ["1m"]
        coros = []
        for pair in pairs:
            pairlist_with_timeframes = []
            for timeframe in timeframes:
                pairlist_with_timeframes.append((pair, timeframe))
            coros.append(self.refresh_latest_ohlcv(pairlist_with_timeframes, since_ms=since_ms))
        for coro in coros:
            await coro

        for pair in pairs:
            for timeframe in timeframes:
                print(self.klines((pair, timeframe)))

    @staticmethod
    def get_ccxt_headers() -> dict[str, str]:
        """
        Return exchange specific HTTP headers dictionary.

        Return a dictionary with extra HTTP headers to pass to ccxt when creating the
        connection instance.
        """
        return {}

    @staticmethod
    def get_ccxt_config() -> dict[str, Any]:
        """
        Return exchange specific configuration dictionary.

        Return a dictionary with extra options to pass to ccxt when creating the
        connection instance.
        """
        return {}

    @classmethod
    def resolve_class(cls, config: BaseConfig) -> type[Exchange]:
        """
        Resolve the exchange class to use based on the configuration.
        """
        # Get rid of the non-slotted subclasses
        # https://www.attrs.org/en/stable/glossary.html?highlight=gc.collect#term-slotted-classes
        gc.collect()
        name = config.exchange.name
        market = config.exchange.market
        for subclass in cls.__subclasses__():
            subclass_name = attrs.fields(subclass).name.default
            subclass_market = attrs.fields(subclass).market.default
            if subclass_name is None or subclass_market is None:
                raise RuntimeError(
                    f"The exchange subclass {subclass.__qualname__} does not define the fields "
                    "name or market. Please fix that."
                )
            if subclass_name == name and market == subclass_market:
                return subclass
        raise OperationalException(
            f"Could not properly resolve the exchange class based on exchange name {name!r} and market {market!r}."
        )

    def ohlcv_candle_limit(self, timeframe: str) -> int:
        """
        Exchange ohlcv candle limit.

        Uses ohlcv_candle_limit_per_timeframe if the exchange has different limits
        per timeframe (e.g. bittrex), otherwise falls back to ohlcv_candle_limit
        :param timeframe: Timeframe to check
        :return: Candle limit as integer
        """
        return int(
            self.exchange_supports.get("ohlcv_candle_limit_per_timeframe", {}).get(
                timeframe,
                self.exchange_supports.get("ohlcv_candle_limit"),
            ),
        )

    async def get_markets(self) -> dict[str, Any]:
        """
        Load the exchange markets.
        """
        if not self._markets:
            log.info("Loading markets")
            self._markets = await self.ccxt_conn.load_markets()
            await self.events.on_markets_available.emit(markets=self._markets)
        return self._markets

    @property
    def markets(self) -> dict[str, Any]:
        """
        Return the loaded markets.
        """
        return self._markets

    async def get_tickers(self) -> dict[str, Any]:
        """
        Return the exchange tickers.
        """
        log.info(
            "Fetching tickers for exchange %s(%s)",
            self.config.exchange.name,
            self.config.exchange.market,
        )
        tickers: dict[str, Any] = await self.ccxt_conn.fetch_tickers()
        log.debug(
            "Fetched %s tickers from %s(%s)",
            len(tickers),
            self.config.exchange.name,
            self.config.exchange.market,
        )
        await self.events.on_tickers_available.emit(tickers=tickers)
        return tickers

    def get_pair_quote_currency(self, pair: str) -> str:
        """
        Return a pair's quote currency.
        """
        quote_currency: str = ""
        if pair in self.markets:
            quote_currency = self.markets[pair].get("quote", "")
        return quote_currency

    async def refresh_latest_ohlcv(
        self,
        pair_list: ListPairsWithTimeframes,
        *,
        since_ms: int | None = None,
        cache: bool = True,
    ) -> dict[tuple[str, str], DataFrame]:
        """
        Refresh in-memory OHLCV asynchronously and set `_klines` with the result.

        Loops asynchronously over pair_list and downloads all pairs async (semi-parallel).
        Only used in the dataprovider.refresh() method.
        :param pair_list: List of 2 element tuples containing pair, interval to refresh
        :param since_ms: time since when to download, in milliseconds
        :param cache: Assign result to _klines. Useful for one-off downloads like for pairlists
        :return: Dict of [{(pair, timeframe): Dataframe}]
        """
        log.debug("Refreshing candle (OHLCV) data for %d pairs", len(pair_list))

        input_coroutines = []
        cached_pairs = []
        # Gather coroutines to run
        for pair, timeframe in set(pair_list):
            if (
                (pair, timeframe) not in self._klines
                or not cache
                or self._now_is_time_to_refresh(pair, timeframe)
            ):
                required_candle_call_count = self.config.exchange.required_candle_call_count
                if not since_ms and required_candle_call_count > 1:
                    # Multiple calls for one pair - to get more history
                    one_call = tf.to_msecs(timeframe) * self.ohlcv_candle_limit(timeframe)
                    move_to = one_call * required_candle_call_count
                    now = tf.to_next_date(timeframe)
                    since_ms = int((now - timedelta(seconds=move_to // 1000)).timestamp() * 1000)

                if since_ms:
                    input_coroutines.append(
                        self.get_historic_ohlcv(pair, timeframe, since_ms=since_ms, raise_=True)
                    )
                else:
                    # One call ... "regular" refresh
                    input_coroutines.append(
                        self.get_candle_history(pair, timeframe, since_ms=since_ms)
                    )
            else:
                log.debug(
                    "Using cached candle (OHLCV) data for pair %s, timeframe %s ...",
                    pair,
                    timeframe,
                )
                cached_pairs.append((pair, timeframe))

        results_df = {}
        # Chunk requests into batches of 100 to avoid overwhelming ccxt Throttling
        for input_coro in chunks(input_coroutines, 100):

            results = await asyncio.gather(*input_coro, return_exceptions=True)

            # handle caching
            for res in results:
                if isinstance(res, Exception):
                    log.warning("Async code raised an exception: %r", res, exc_info=True)
                    continue
                # Deconstruct tuple (has 3 elements)
                pair, timeframe, ticks = res
                # keeping last candle time as last refreshed time of the pair
                if ticks:
                    self._pairs_last_refresh_time[(pair, timeframe)] = ticks[-1][0] // 1000
                # keeping parsed dataframe in cache
                ohlcv_df = ohlcv_to_dataframe(
                    ticks,
                    timeframe,
                    pair=pair,
                    fill_missing=True,
                    drop_incomplete=True,
                    # drop_incomplete=self._ohlcv_partial_candle,
                )
                results_df[(pair, timeframe)] = ohlcv_df
                if cache:
                    self._klines[(pair, timeframe)] = ohlcv_df

        # Return cached klines
        for pair, timeframe in cached_pairs:
            results_df[(pair, timeframe)] = self.klines((pair, timeframe), copy=False)

        return results_df

    async def get_historic_ohlcv(
        self,
        pair: str,
        timeframe: str,
        since_ms: int,
        raise_: bool = False,
    ) -> DataFrame | list[dict[str, Any]]:
        """
        Get candle history using asyncio and returns the list of candles.

        :param pair: Pair to download
        :param timeframe: Timeframe to get data for
        :param since_ms: Timestamp in milliseconds to get history from
        :return: List with candle (OHLCV) data
        """
        one_call = tf.to_msecs(timeframe) * self.ohlcv_candle_limit(timeframe)
        log.debug(
            "one_call: %s msecs (%s)",
            one_call,
            arrow.utcnow().shift(seconds=one_call // 1000).humanize(only_distance=True),
        )
        input_coroutines = [
            self.get_candle_history(pair, timeframe, since)
            for since in range(since_ms, arrow.utcnow().int_timestamp * 1000, one_call)
        ]

        data: list[Any] = []
        # Chunk requests into batches of 100 to avoid overwhelming ccxt Throttling
        for input_coro in chunks(input_coroutines, 100):

            results = await asyncio.gather(*input_coro, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    log.warning("Async code raised an exception: %s", res, exc_info=res)
                    if raise_:
                        raise  # pylint: disable=misplaced-bare-raise
                    continue
                else:
                    # Deconstruct tuple if it's not an exception
                    pair_, _, new_data = res
                    if pair_ == pair:
                        data.extend(new_data)
        # Sort data again after extending the result - above calls return in "async order"
        data = sorted(data, key=operator.itemgetter(0))
        return pair, timeframe, data

    @async_retrier
    async def get_candle_history(
        self, pair: str, timeframe: str, since_ms: int | None = None
    ) -> tuple[str, str, list[Any]]:
        """
        Asynchronously get candle history data using fetch_ohlcv.

        returns tuple: (pair, timeframe, ohlcv_list)
        """
        try:
            # Fetch OHLCV asynchronously
            since = f"({arrow.get(since_ms // 1000).isoformat()}) " if since_ms is not None else ""
            log.debug(
                "Fetching pair %s, interval %s, since %s %s...", pair, timeframe, since_ms, since
            )
            params = self.exchange_supports.get("ohlcv_params", {})
            data = await self.ccxt_conn.fetch_ohlcv(
                pair,
                timeframe=timeframe,
                since=since_ms,
                limit=self.ohlcv_candle_limit(timeframe),
                params=params,
            )

            # Some exchanges sort OHLCV in ASC order and others in DESC.
            # Ex: Bittrex returns the list of OHLCV in ASC order (oldest first, newest last)
            # while GDAX returns the list of OHLCV in DESC order (newest first, oldest last)
            # Only sort if necessary to save computing time
            try:
                if data and data[0][0] > data[-1][0]:
                    data = sorted(data, key=operator.itemgetter(0))
            except IndexError:
                log.exception("Error loading %s. Result was %s.", pair, data)
                return pair, timeframe, []
            log.debug(
                "Done fetching pair %s, interval %s, since %s %s ...",
                pair,
                timeframe,
                since_ms,
                since,
            )
            return pair, timeframe, data

        except ccxt.NotSupported as exc:
            raise OperationalException(
                f"Exchange {self.config.exchange.name} does not support fetching historical "
                f"candle (OHLCV) data. Message: {exc}"
            ) from exc
        except ccxt.DDoSProtection as exc:
            raise DDosProtection(exc) from exc
        except (ccxt.NetworkError, ccxt.ExchangeError) as exc:
            raise TemporaryError(
                f"Could not fetch historical candle (OHLCV) data for pair {pair} due "
                f"to {exc.__class__.__name__}. Message: {exc}"
            ) from exc
        except ccxt.BaseError as exc:
            raise OperationalException(
                f"Could not fetch historical candle (OHLCV) data for pair {pair}. Message: {exc}"
            ) from exc

    def klines(self, pair_interval: tuple[str, str], copy: bool = True) -> DataFrame:
        """
        Return the klines dataframe.
        """
        if pair_interval in self._klines:
            ret = self._klines[pair_interval]
            if copy:
                return ret.copy()
            return ret
        return DataFrame()

    def _now_is_time_to_refresh(self, pair: str, timeframe: str) -> bool:
        """
        Check it the pair needs to be refreshed.
        """
        # Timeframe in seconds
        interval_in_sec = tf.to_seconds(timeframe)
        last_refresh_time = (
            self._pairs_last_refresh_time.get((pair, timeframe), 0) + interval_in_sec
        )
        is_time_to_refresh: bool = last_refresh_time < arrow.utcnow().int_timestamp
        return is_time_to_refresh
