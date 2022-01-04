"""
Binance exchange implementation.
"""
from __future__ import annotations

from typing import Any

from mcookbook.exchanges.abc import Exchange
from mcookbook.utils import merge_dictionaries


class BinanceFutures(Exchange):
    """
    Binance futures exchange implementation.
    """

    _name: str = "binance"
    _market: str = "future"

    def _get_ccxt_config(self) -> dict[str, Any]:
        ccxt_config = super()._get_ccxt_config() or {}
        return merge_dictionaries(ccxt_config, {"options": {"defaultType": self._market}})
