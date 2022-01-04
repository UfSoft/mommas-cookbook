"""
PairList base class.
"""
from __future__ import annotations

import copy
import logging
from typing import Any
from typing import TYPE_CHECKING

from pydantic import BaseModel
from pydantic import Field
from pydantic import PrivateAttr

from mcookbook.exceptions import OperationalException
from mcookbook.pairlist.manager import PairListManager

if TYPE_CHECKING:
    from mcookbook.config.live import LiveConfig
    from mcookbook.exchanges.abc import Exchange


log = logging.getLogger(__name__)


class PairList(BaseModel):
    """
    Base pair list implementation.
    """

    _enabled: bool = PrivateAttr(default=True)
    _position: int = PrivateAttr(default=0)
    _last_refresh: int = PrivateAttr(default=0)
    _exchange: Exchange = PrivateAttr()

    name: str
    refresh_period: int = Field(default=1800, ge=0)

    @classmethod
    def resolved(cls, config: dict[str, Any]) -> PairList:
        """
        Resolve the passed ``name`` to class implementation.
        """
        if "name" not in config:
            raise ValueError("The 'name' key is missing.")
        for subclass in cls.__subclasses__():
            subclass_name = subclass.__name__  # pylint: disable=protected-access
            if subclass_name == config["name"]:
                return subclass.parse_obj(config)
        raise OperationalException("Cloud not find an {config['name']} pair list implementation.")

    @property
    def exchange(self) -> Exchange:
        """
        Return the exchange class instance.
        """
        return self._exchange

    @property
    def config(self) -> LiveConfig:
        """
        Return the loaded configuration.
        """
        return self._exchange.config

    @property
    def pairlist_manager(self) -> PairListManager:
        """
        Return the pair list manager.
        """
        manager: PairListManager = self._exchange.pairlist_manager
        return manager

    @property
    def needstickers(self) -> bool:
        """
        Boolean property defining if tickers are necessary.

        If no PairList requires tickers, an empty Dict is passed
        as tickers argument to filter_pairlist
        """
        return False

    def _validate_pair(self, pair: str, ticker: dict[str, Any]) -> bool:
        """
        Check one pair against Pairlist Handler's specific conditions.

        Either implement it in the Pairlist Handler or override the generic
        filter_pairlist() method.

        :param pair: Pair that's currently validated
        :param ticker: ticker dict as returned from ccxt.fetch_tickers()
        :return: True if the pair can stay, false if it should be removed
        """
        raise NotImplementedError()

    def gen_pairlist(self, tickers: dict[str, Any]) -> list[str]:
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

    def filter_pairlist(self, pairlist: list[str], tickers: dict[str, Any]) -> list[str]:
        """
        Filters and sorts pairlist and returns the whitelist again.

        Called on each bot iteration - please use internal caching if necessary
        This generic implementation calls self._validate_pair() for each pair
        in the pairlist.

        Some Pairlist Handlers override this generic implementation and employ
        own filtration.

        :param pairlist: pairlist to filter or sort
        :param tickers: Tickers (from exchange.get_tickers()). May be cached.
        :return: new whitelist
        """
        if self._enabled:
            # Copy list since we're modifying this list
            for p in copy.deepcopy(pairlist):
                # Filter out assets
                if not self._validate_pair(p, tickers[p] if p in tickers else {}):
                    pairlist.remove(p)

        return pairlist

    def verify_blacklist(self, pairlist: list[str]) -> list[str]:
        """
        Proxy method to verify_blacklist for easy access for child classes.

        :param pairlist: Pairlist to validate
        :param logmethod: Function that'll be called, `logger.info` or `logger.warning`.
        :return: pairlist - blacklisted pairs
        """
        return self.pairlist_manager.verify_blacklist(pairlist)

    def verify_whitelist(self, pairlist: list[str], keep_invalid: bool = False) -> list[str]:
        """
        Proxy method to verify_whitelist for easy access for child classes.

        :param pairlist: Pairlist to validate
        :param logmethod: Function that'll be called, `logger.info` or `logger.warning`
        :param keep_invalid: If sets to True, drops invalid pairs silently while expanding regexes.
        :return: pairlist - whitelisted pairs
        """
        return self.pairlist_manager.verify_whitelist(pairlist, keep_invalid)

    def _whitelist_for_active_markets(self, pairlist: list[str]) -> list[str]:
        """
        Check available markets and remove pair from whitelist if necessary.

        :param pairlist: the sorted list of pairs the user might want to trade
        :return: the list of pairs the user wants to trade without those unavailable or
        black_listed
        """
        markets = self.exchange.api.markets
        if not markets:
            raise OperationalException(
                "Markets not loaded. Make sure that exchange is initialized correctly."
            )

        sanitized_whitelist: list[str] = []
        for pair in pairlist:
            # pair is not in the generated dynamic market or has the wrong stake currency
            if pair not in markets:
                log.warning(
                    "Pair '%s' is not compatible with exchange %s Removing it from whitelist..",
                    pair,
                    self.config.exchange.name,
                )
                continue

            #            if not self._exchange.market_is_tradable(markets[pair]):
            #                self.log_once(f"Pair {pair} is not tradable with Freqtrade."
            #                              "Removing it from whitelist..", logger.warning)
            #                continue
            #
            #            if self._exchange.get_pair_quote_currency(pair) != self._config['stake_currency']:
            #                self.log_once(f"Pair {pair} is not compatible with your stake currency "
            #                              f"{self._config['stake_currency']}. Removing it from whitelist..",
            #                              logger.warning)
            #                continue

            #            # Check if market is active
            #            market = markets[pair]
            #            if not market_is_active(market):
            #                self.log_once(f"Ignoring {pair} from whitelist. Market is not active.", logger.info)
            #                continue
            if pair not in sanitized_whitelist:
                sanitized_whitelist.append(pair)

        # We need to remove pairs that are unknown
        return sanitized_whitelist
