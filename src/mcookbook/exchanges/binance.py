"""
Binance exchange implementation.
"""
from __future__ import annotations

from typing import Any

import attrs

from mcookbook.exchanges.abc import Exchange


@attrs.define(kw_only=True)
class BinanceFutures(Exchange):
    """
    Binance futures exchange implementation.
    """

    name = attrs.field(default="binance", on_setattr=attrs.setters.frozen)
    market = attrs.field(default="future", on_setattr=attrs.setters.frozen)

    @staticmethod
    def get_ccxt_config() -> dict[str, Any]:
        """
        Exchange specific ccxt configuration.

        Return a dictionary with extra options to pass to ccxt when creating the
        connection instance.
        """
        return {"options": {"defaultType": attrs.fields(BinanceFutures).market.default}}
