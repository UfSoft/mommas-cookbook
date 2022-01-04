"""
Binance exchange implementation.
"""
from __future__ import annotations

from mcookbook.exchanges.abc import Exchange


class BinanceFutures(Exchange):
    """
    Binance futures exchange implementation.
    """

    _name: str = "binance"
    _market: str = "futures"
