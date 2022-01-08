"""
Base exchange class implementation.
"""
from __future__ import annotations

import asyncio
import logging
import pprint
from datetime import timedelta
from typing import Any

import ccxt
from ccxt.async_support import Exchange as CCXTExchange
from polars import DataFrame
from pydantic import BaseModel
from pydantic import PrivateAttr

from mcookbook.config.live import LiveConfig
from mcookbook.exceptions import OperationalException
from mcookbook.pairlist.manager import PairListManager
from mcookbook.utils import chunks
from mcookbook.utils import merge_dictionaries
from mcookbook.utils import timeframe_to_msecs
from mcookbook.utils import timeframe_to_next_date
from mcookbook.utils.data import ohlcv_to_dataframe

log = logging.getLogger(__name__)

PairWithTimeframe = tuple[str, str]
ListPairsWithTimeframes = list[PairWithTimeframe]
OhlcvDict = dict[tuple[str, str], DataFrame]


class Exchange(BaseModel):
    """
    Base Exchange class.
    """

    _name: str = PrivateAttr()
    _market: str = PrivateAttr()

    config: LiveConfig

    _api: type[CCXTExchange] = PrivateAttr()
    _markets: dict[str, dict[str, Any]] = PrivateAttr(default_factory=dict)
    _pairlist_manager: PairListManager = PrivateAttr()
    _klines: dict[tuple[str, str], DataFrame] = PrivateAttr(default_factory=dict)

    def _get_ccxt_headers(self) -> dict[str, str] | None:
        return None

    def _get_ccxt_config(self) -> dict[str, Any] | None:
        return None

    @classmethod
    def resolved(cls, config: LiveConfig) -> Exchange:
        """
        Resolve the passed ``name`` and ``market`` to class implementation.
        """
        name = config.exchange.name
        market = config.exchange.market
        for subclass in cls.__subclasses__():
            subclass_name = subclass._name  # pylint: disable=protected-access
            subclass_market = subclass._market  # pylint: disable=protected-access
            if subclass_name == name and market == subclass_market:
                instance = subclass.parse_obj({"config": config.dict()})
                instance._pairlist_manager = PairListManager.construct(config=config)
                instance._pairlist_manager._exchange = instance
                for handler in config.pairlists:
                    handler._exchange = instance
                instance._pairlist_manager._pairlist_handlers = config.pairlists
                return instance
        raise OperationalException(
            f"Cloud not find an implementation for the {name}(market={market}) exchange."
        )

    @property
    def api(self) -> CCXTExchange:
        """
        Instantiate and return a CCXT exchange class.
        """
        try:
            return self._api
        except AttributeError:
            log.info("Using CCXT %s", ccxt.__version__)
            ccxt_config = self.config.exchange.get_ccxt_config()
            exchange_ccxt_config = self._get_ccxt_config()  # pylint: disable=assignment-from-none
            if exchange_ccxt_config:
                merge_dictionaries(ccxt_config, exchange_ccxt_config)
            headers = self._get_ccxt_headers()  # pylint: disable=assignment-from-none
            if headers:
                merge_dictionaries(ccxt_config, {"headers": headers})
            log.info(
                "Instantiating API for the '%s' exchange with the following configuration:\n%s",
                self.config.exchange.name,
                pprint.pformat(ccxt_config),
            )
            # Reveal secrets
            for key in ("apiKey", "secret", "password", "uid"):
                if key not in ccxt_config:
                    continue
                ccxt_config[key] = ccxt_config[key].get_secret_value()
            try:
                self._api = getattr(ccxt.async_support, self.config.exchange.name)(ccxt_config)
            except (KeyError, AttributeError) as exc:
                raise OperationalException(
                    f"Exchange {self.config.exchange.name} is not supported"
                ) from exc
            except ccxt.BaseError as exc:
                raise OperationalException(f"Initialization of ccxt failed. Reason: {exc}") from exc
        return self._api

    async def get_markets(self) -> dict[str, Any]:
        """
        Load the exchange markets.
        """
        if not self._markets:
            log.info("Loading markets")
            self._markets = await self.api.load_markets()
        return self._markets

    @property
    def markets(self) -> dict[str, Any]:
        """
        Return the loaded markets.
        """
        return self._markets

    @property
    def pairlist_manager(self) -> PairListManager:
        """
        Return the pair list manager.
        """
        return self._pairlist_manager

    async def refresh_latest_ohlcv(
        self,
        pair_list: ListPairsWithTimeframes,
        *,
        since_ms: int | None = None,
        cache: bool = True,
    ) -> OhlcvDict:
        """
        Refresh in-memory OHLCV asynchronously and set `_klines` with the result
        Loops asynchronously over pair_list and downloads all pairs async (semi-parallel).
        Only used in the dataprovider.refresh() method.
        :param pair_list: List of 2 element tuples containing pair, interval to refresh
        :param since_ms: time since when to download, in milliseconds
        :param cache: Assign result to _klines. Usefull for one-off downloads like for pairlists
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
                if not since_ms and self.required_candle_call_count > 1:
                    # Multiple calls for one pair - to get more history
                    one_call = timeframe_to_msecs(timeframe) * self.ohlcv_candle_limit(timeframe)
                    move_to = one_call * self.required_candle_call_count
                    now = timeframe_to_next_date(timeframe)
                    since_ms = int((now - timedelta(seconds=move_to // 1000)).timestamp() * 1000)

                if since_ms:
                    input_coroutines.append(
                        self._async_get_historic_ohlcv(
                            pair, timeframe, since_ms=since_ms, raise_=True
                        )
                    )
                else:
                    # One call ... "regular" refresh
                    input_coroutines.append(
                        self._async_get_candle_history(pair, timeframe, since_ms=since_ms)
                    )
            else:
                log.debug(
                    "Using cached candle (OHLCV) data for pair %s, timeframe %s ...",
                    pair,
                    timeframe,
                )
                cached_pairs.append((pair, timeframe))

        results_df = {}
        # Chunk requests into batches of 100 to avoid overwelming ccxt Throttling
        for input_coro in chunks(input_coroutines, 100):

            results = await asyncio.gather(*input_coro, return_exceptions=True)

            # handle caching
            for res in results:
                if isinstance(res, Exception):
                    log.warning("Async code raised an exception: %r", res)
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
                    drop_incomplete=self._ohlcv_partial_candle,
                )
                results_df[(pair, timeframe)] = ohlcv_df
                if cache:
                    self._klines[(pair, timeframe)] = ohlcv_df

        # Return cached klines
        for pair, timeframe in cached_pairs:
            results_df[(pair, timeframe)] = self.klines((pair, timeframe), copy=False)

        return results_df
