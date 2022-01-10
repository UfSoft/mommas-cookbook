"""
Volume pair list handler.
"""
# pylint: disable=no-member,not-an-iterable,unsubscriptable-object,invalid-unary-operand-type
from __future__ import annotations

import logging
import operator
from typing import Any

import arrow
import attrs
from cachetools import TTLCache

import mcookbook.utils.tf as tf
from mcookbook.config.pairlist import VolumePairListConfig
from mcookbook.exceptions import OperationalException
from mcookbook.pairlist.abc import PairList

log = logging.getLogger(__name__)


@attrs.define(kw_only=True)
class VolumePairList(PairList):
    """
    Static pair list handler.
    """

    config: VolumePairListConfig = attrs.field()

    _tf_in_minutes: int = attrs.field(init=False, repr=False)
    _tf_in_seconds: int = attrs.field(init=False, repr=False)
    _use_range: bool = attrs.field(init=False, repr=False)
    _pair_cache: TTLCache[str, list[str]] = attrs.field(init=False, repr=False)

    @_tf_in_minutes.default  # type: ignore[attr-defined,misc]
    def _set_tf_in_minutes(self) -> int:
        return tf.to_minutes(self.config.lookback_timeframe)

    @_tf_in_seconds.default  # type: ignore[attr-defined,misc]
    def _set_tf_in_seconds(self) -> int:
        return self._tf_in_minutes * 60

    @_use_range.default  # type: ignore[attr-defined,misc]
    def _set_use_range(self) -> bool:
        use_range = False
        if self._tf_in_minutes > 0 and self.config.lookback_period > 0:
            use_range = True
        if use_range and self.config.refresh_period < self._tf_in_seconds:
            raise ValueError(
                f"Refresh period of {self.config.refresh_period} seconds is smaller than one "
                f"timeframe of {self.config.lookback_timeframe}. Please adjust refresh_period "
                f"to at least {self._tf_in_seconds} and restart."
            )
        return use_range

    @_pair_cache.default  # type: ignore[attr-defined,misc]
    def _set_pair_cache(self) -> TTLCache[str, list[str]]:
        return TTLCache(maxsize=1, ttl=self.config.refresh_period)

    def __attrs_post_init__(self) -> None:
        """
        Post attrs, initialization routines.
        """
        max_request_size = self.exchange.ohlcv_candle_limit(self.config.lookback_timeframe)
        if self.config.lookback_period > max_request_size:
            raise OperationalException(
                "VolumeFilter requires lookback_period to not exceed exchange max request "
                f"size ({max_request_size})"
            )

    @property
    def needstickers(self) -> bool:
        """
        Boolean property defining if tickers are necessary.

        If no Pairlist requires tickers, an empty Dict is passed
        as tickers argument to filter_pairlist
        """
        return True

    async def gen_pairlist(self, tickers: dict[str, Any]) -> list[str]:
        """
        Generate the pairlist.

        :param tickers: Tickers (from exchange.get_tickers()). May be cached.
        :return: List of pairs
        """
        # Generate dynamic allow_list
        # Must always run if this pairlist is not the first in the list.
        pairlist: list[str] | None = self._pair_cache.get("pairlist")
        if pairlist:
            # Item found - no refresh necessary
            return pairlist.copy()
        # Use fresh pairlist
        # Check if pair quote currency equals to the stake currency.
        filtered_tickers = [
            ticker
            for pair, ticker in tickers.items()
            if (
                self.exchange.get_pair_quote_currency(pair) == self.exchange.config.stake_currency
                and (self._use_range or ticker[self.config.sort_key] is not None)
            )
        ]
        pairlist = [ticker["symbol"] for ticker in filtered_tickers]

        pairlist = await self.filter_pairlist(pairlist, tickers)
        # pylint: disable=unsupported-assignment-operation
        self._pair_cache["pairlist"] = pairlist.copy()
        # pylint: enable=unsupported-assignment-operation
        return pairlist

    async def filter_pairlist(self, pairlist: list[str], tickers: dict[str, Any]) -> list[str]:
        """
        Filters and sorts pairlist and returns the allow_list again.

        Called on each bot iteration - please use internal caching if necessary
        :param pairlist: pairlist to filter or sort
        :param tickers: Tickers (from exchange.get_tickers()). May be cached.
        :return: new allow_list
        """
        # Use the incoming pairlist.
        filtered_tickers = [v for k, v in tickers.items() if k in pairlist]

        # get lookback period in ms, for exchange ohlcv fetch
        if self._use_range:
            since_ms = (
                int(
                    arrow.utcnow()
                    .floor("minute")
                    .shift(
                        minutes=-(self.config.lookback_period * self._tf_in_minutes)
                        - self._tf_in_minutes
                    )
                    .int_timestamp
                )
                * 1000
            )

            to_ms = (
                int(
                    arrow.utcnow().floor("minute").shift(minutes=-self._tf_in_minutes).int_timestamp
                )
                * 1000
            )

            # TODO: utc date output for starting date
            log.info(  # type: ignore[call-arg]
                "Using volume range of %s candles, timeframe: %s, starting from %s till %s",
                self.config.lookback_period,
                self.config.lookback_timeframe,
                tf.format_ms_time(since_ms),
                tf.format_ms_time(to_ms),
                once_every_secs=self.config.refresh_period,
            )
            needed_pairs = [
                (pair, self.config.lookback_timeframe)
                for pair in [ticker["symbol"] for ticker in filtered_tickers]
                if pair not in self._pair_cache  # pylint: disable=unsupported-membership-test
            ]

            # Get all candles
            candles = {}
            if needed_pairs:
                candles = await self.exchange.refresh_latest_ohlcv(
                    needed_pairs, since_ms=since_ms, cache=False
                )
            for idx, ticker in enumerate(filtered_tickers):
                pair_candles = (
                    candles[(ticker["symbol"], self.config.lookback_timeframe)]
                    if (ticker["symbol"], self.config.lookback_timeframe) in candles
                    else None
                )
                # in case of candle data calculate typical price and quoteVolume for candle
                if pair_candles is not None and not pair_candles.empty:
                    pair_candles["typical_price"] = (
                        pair_candles["high"] + pair_candles["low"] + pair_candles["close"]
                    ) / 3
                    pair_candles["quoteVolume"] = (
                        pair_candles["volume"] * pair_candles["typical_price"]
                    )

                    # ensure that a rolling sum over the lookback_period is built
                    # if pair_candles contains more candles than lookback_period
                    quote_volume = (
                        pair_candles["quoteVolume"]
                        .rolling(self.config.lookback_period)
                        .sum()
                        .iloc[-1]
                    )

                    # replace quoteVolume with range quoteVolume sum calculated above
                    filtered_tickers[idx]["quoteVolume"] = quote_volume
                else:
                    filtered_tickers[idx]["quoteVolume"] = 0

        if self.config.min_value > 0:
            filtered_tickers = [
                ticker
                for ticker in filtered_tickers
                if ticker[self.config.sort_key] > self.config.min_value
            ]

        sorted_tickers: list[dict[str, Any]] = sorted(
            filtered_tickers, reverse=True, key=operator.itemgetter(self.config.sort_key)
        )

        # Validate allow_list to only have active market pairs
        pairs: list[str] = self._allow_list_for_active_markets(
            [ticker["symbol"] for ticker in sorted_tickers]
        )
        pairs = self.verify_block_list(pairs)
        # Limit pairlist to the requested number of pairs
        pairs = pairs[: self.config.number_assets]

        log.info(  # type: ignore[call-arg]
            "Searching %d pairs: %s",
            self.config.number_assets,
            pairs,
            once_every_secs=self.config.refresh_period,
        )
        return pairs
