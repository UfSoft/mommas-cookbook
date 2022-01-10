"""
Live trading service.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import attrs

from mcookbook.cli.abc import CLIService
from mcookbook.pairlist.manager import PairListManager
from mcookbook.utils.ccxt import CCXTExchange

if TYPE_CHECKING:
    from mcookbook.config.trade import TradeConfig


@attrs.define(kw_only=True)
class TradeService(CLIService):
    """
    Live trading service implementation.
    """

    config: TradeConfig
    ccxt_conn: CCXTExchange
    pairlist_manager: PairListManager

    async def work(self) -> None:
        """
        Routines to run the service.
        """
        # assert self.exchange.api  # Load ccxt api
        # await self.exchange.get_markets()
        # await self.exchange.pairlist_manager.refresh_pairlist()

        while True:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break

    async def await_closed(self) -> None:
        """
        Run shutdown routines.
        """
        # if self.exchange:
        #    await self.exchange.api.close()
        return await super().await_closed()
