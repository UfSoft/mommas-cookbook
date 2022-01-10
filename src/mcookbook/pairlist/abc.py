"""
PairList base class.
"""
# pylint: disable=no-member,not-an-iterable,unsubscriptable-object
from __future__ import annotations

import copy
import logging
from typing import Any
from typing import TYPE_CHECKING

import attrs

from mcookbook.exceptions import OperationalException
from mcookbook.pairlist.manager import PairListManager


log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from mcookbook.config.exchange import ExchangeConfig
    from mcookbook.config.pairlist import PairListConfig
    from mcookbook.exchanges.abc import Exchange
    from mcookbook.utils.ccxt import CCXTExchange


@attrs.define(kw_only=True)
class PairList:
    """
    Base pair list implementation.
    """

    name: str = attrs.field()
    config: PairListConfig = attrs.field()
    exchange: Exchange = attrs.field()
    ccxt_conn: CCXTExchange = attrs.field()
    pairlist_manager: PairListManager = attrs.field()

    _position: int = attrs.field(default=0, repr=False)
    _last_refresh: int = attrs.field(default=0, repr=False)

    @property
    def exchange_config(self) -> ExchangeConfig:
        """
        Return the exchange configuration.
        """
        return self.exchange.config.exchange

    @property
    def needstickers(self) -> bool:
        """
        Boolean property defining if tickers are necessary.

        If no PairList requires tickers, an empty Dict is passed
        as tickers argument to filter_pairlist
        """
        return False

    def _validate_pair(
        self, pair: str, ticker: dict[str, Any]  # pylint: disable=unused-argument
    ) -> bool:
        """
        Check one pair against Pairlist Handler's specific conditions.

        Either implement it in the Pairlist Handler or override the generic
        filter_pairlist() method.

        :param pair: Pair that's currently validated
        :param ticker: ticker dict as returned from ccxt.fetch_tickers()
        :return: True if the pair can stay, false if it should be removed
        """
        return True

    async def gen_pairlist(self, tickers: dict[str, Any]) -> list[str]:
        """
        Generate the pairlist.

        This method is called once by the pairlistmanager in the refresh_pairlist()
        method to supply the starting pairlist for the chain of the Pairlist Handlers.
        Pairlist Filters (those Pairlist Handlers that cannot be used at the first
        position in the chain) shall not override this base implementation --
        it will raise the exception if a Pairlist Handler is used at the first
        position in the chain.

        :param tickers: Tickers (from exchange.get_tickers()). May be cached.
        :return: List of pairs
        """
        raise OperationalException(
            "This Pairlist Handler should not be used "
            "at the first position in the list of Pairlist Handlers."
        )

    async def filter_pairlist(self, pairlist: list[str], tickers: dict[str, Any]) -> list[str]:
        """
        Filters and sorts pairlist and returns the allow_list again.

        Called on each bot iteration - please use internal caching if necessary
        This generic implementation calls self._validate_pair() for each pair
        in the pairlist.

        Some Pairlist Handlers override this generic implementation and employ
        own filtration.

        :param pairlist: pairlist to filter or sort
        :param tickers: Tickers (from exchange.get_tickers()). May be cached.
        :return: new allow_list
        """
        # Copy list since we're modifying this list
        for pair in copy.deepcopy(pairlist):
            # Filter out assets
            if not self._validate_pair(pair, tickers[pair] if pair in tickers else {}):
                pairlist.remove(pair)

        return pairlist

    def verify_block_list(self, pairlist: list[str]) -> list[str]:
        """
        Proxy method to verify_block_list for easy access for child classes.

        :param pairlist: Pairlist to validate
        :return: pairlist - block_listed pairs
        """
        return self.pairlist_manager.verify_block_list(pairlist)

    def verify_allow_list(self, pairlist: list[str], keep_invalid: bool = False) -> list[str]:
        """
        Proxy method to verify_allow_list for easy access for child classes.

        :param pairlist: Pairlist to validate
        :param keep_invalid: If sets to True, drops invalid pairs silently while expanding regexes.
        :return: pairlist - allow_listed pairs
        """
        return self.pairlist_manager.verify_allow_list(pairlist, keep_invalid)

    def _allow_list_for_active_markets(self, pairlist: list[str]) -> list[str]:
        """
        Check available markets and remove pair from allow_list if necessary.

        :param pairlist: the sorted list of pairs the user might want to trade
        :return: the list of pairs the user wants to trade without those unavailable or
        black_listed
        """
        markets = self.ccxt_conn.markets
        if not markets:
            raise OperationalException(
                "Markets not loaded. Make sure that exchange is initialized correctly."
            )

        sanitized_allow_list: list[str] = []
        for pair in pairlist:
            # pair is not in the generated dynamic market or has the wrong stake currency
            if pair not in markets:
                log.warning(
                    "Pair '%s' is not compatible with exchange %s Removing it from allow_list..",
                    pair,
                    self.exchange.name,
                )
                continue

            #            if not self._exchange.market_is_tradable(markets[pair]):
            #                self.log_once(f"Pair {pair} is not tradable with Freqtrade."
            #                              "Removing it from allow_list..", logger.warning)
            #                continue
            #
            #            if self._exchange.get_pair_quote_currency(pair) != self._config['stake_currency']:
            #                self.log_once(f"Pair {pair} is not compatible with your stake currency "
            #                              f"{self._config['stake_currency']}. Removing it from allow_list..",
            #                              logger.warning)
            #                continue

            #            # Check if market is active
            #            market = markets[pair]
            #            if not market_is_active(market):
            #                self.log_once(f"Ignoring {pair} from allow_list. Market is not active.", logger.info)
            #                continue
            if pair not in sanitized_allow_list:
                sanitized_allow_list.append(pair)

        # We need to remove pairs that are unknown
        return sanitized_allow_list
