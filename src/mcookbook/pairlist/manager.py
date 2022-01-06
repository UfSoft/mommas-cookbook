"""
Pair list manager.
"""
from __future__ import annotations

import logging
from typing import Any
from typing import TYPE_CHECKING

from cachetools import cached
from cachetools import TTLCache
from ccxt.async_support import Exchange as CCXTExchange
from pydantic import BaseModel
from pydantic import PrivateAttr

from mcookbook.utils import expand_pairlist

if TYPE_CHECKING:
    from mcookbook.config.live import LiveConfig
    from mcookbook.exchanges.abc import Exchange
    from mcookbook.pairlist import PairList

log = logging.getLogger(__name__)


class PairListManager(BaseModel):
    """
    Pair list manager.
    """

    _allow_list: list[str] = PrivateAttr(default_factory=list)
    _block_list: list[str] = PrivateAttr(default_factory=list)
    _pairlist_handlers: list[PairList] = PrivateAttr(default_factory=list)
    _tickers_needed: bool = PrivateAttr(default=False)
    _exchange: Exchange = PrivateAttr()
    config: LiveConfig

    def __init__(self, config: LiveConfig) -> None:
        super().__init__(config=config)
        for pair in self.config.exchange.pair_allow_list:
            self._allow_list.append(pair)
        for pair in self.config.exchange.pair_block_list:
            self._block_list.append(pair)
        for handler in self._pairlist_handlers:
            self._tickers_needed |= handler.needstickers

    @property
    def exchange(self) -> CCXTExchange:
        """
        Return the CCTX exchange instance.
        """
        return self._exchange.api

    @property
    def expanded_blacklist(self) -> list[str]:
        """
        The expanded blacklist (including wildcard expansion).
        """
        return expand_pairlist(self._block_list, list(self._exchange.markets))

    @cached(TTLCache(maxsize=1, ttl=1800))
    async def _get_cached_tickers(self) -> dict[str, Any]:
        log.info("Fetching tickers for exchange %s", self.config.exchange.name)
        tickers: dict[str, Any] = await self.exchange.get_tickers()
        return tickers

    async def refresh_pairlist(self) -> None:
        """
        Run pairlist through all configured Pairlist Handlers.
        """
        # Tickers should be cached to avoid calling the exchange on each call.
        tickers: dict[str, Any] = {}
        if self._tickers_needed:
            tickers = await self._get_cached_tickers()

        # Generate the pairlist with first Pairlist Handler in the chain
        pairlist = self._pairlist_handlers[0].gen_pairlist(tickers)

        # Process all Pairlist Handlers in the chain
        # except for the first one, which is the generator.
        for pairlist_handler in self._pairlist_handlers[1:]:
            pairlist = pairlist_handler.filter_pairlist(pairlist, tickers)

        # Validation against blacklist happens after the chain of Pairlist Handlers
        # to ensure blacklist is respected.
        pairlist = self.verify_blacklist(pairlist)

        self._allow_list = pairlist
        log.info("Loaded pair list: %s", self._allow_list)

    def verify_blacklist(self, pairlist: list[str]) -> list[str]:
        """
        Verify and remove items from pairlist - returning a filtered pairlist.

        :param pairlist: Pairlist to validate
        :return: pairlist - blacklisted pairs
        """
        try:
            blacklist = self.expanded_blacklist
        except ValueError as err:
            log.error("Pair blacklist contains an invalid Wildcard: %s", err)
            return []
        for pair in pairlist.copy():
            if pair in blacklist:
                log.warning("Pair %s in your blacklist. Removing it from whitelist...", pair)
                pairlist.remove(pair)
        return pairlist

    def verify_whitelist(self, pairlist: list[str], keep_invalid: bool = False) -> list[str]:
        """
        Verify and remove items from pairlist - returning a filtered pairlist.

        :param pairlist: Pairlist to validate
        :param keep_invalid: If sets to True, drops invalid pairs silently while expanding regexes.
        :return: pairlist - whitelisted pairs
        """
        try:

            whitelist = expand_pairlist(pairlist, list(self._exchange.markets), keep_invalid)
        except ValueError as err:
            log.error("Pair whitelist contains an invalid Wildcard: %s", err)
            return []
        return whitelist
