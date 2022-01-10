"""
CCXT related utilities.
"""
from __future__ import annotations

import logging
import pprint
from typing import TYPE_CHECKING

import ccxt
from ccxt.async_support import Exchange as CCXTExchange

from mcookbook.exceptions import OperationalException
from mcookbook.utils.dicts import merge_dictionaries

if TYPE_CHECKING:
    from mcookbook.config.base import BaseConfig
    from mcookbook.exchanges.abc import Exchange

__all__ = [
    "CCXTExchange",
    "create_ccxt_conn",
]

log = logging.getLogger(__name__)


def create_ccxt_conn(config: BaseConfig, exchange_class: Exchange) -> CCXTExchange:
    """
    Create a ccxt connection.
    """
    log.info("Using CCXT %s", ccxt.__version__)
    ccxt_config = config.exchange.get_ccxt_config()
    exchange_ccxt_config = exchange_class.get_ccxt_config()
    if exchange_ccxt_config:
        merge_dictionaries(ccxt_config, exchange_ccxt_config)
    headers = exchange_class.get_ccxt_headers()
    if headers:
        merge_dictionaries(ccxt_config, {"headers": headers})
    log.info(
        "Instantiating API for the %s(%s) exchange with the following configuration:\n%s",
        config.exchange.name,
        config.exchange.market,
        pprint.pformat(ccxt_config),
    )
    # Reveal secrets
    for key in ("apiKey", "secret", "password", "uid"):
        if key not in ccxt_config:
            continue
        ccxt_config[key] = ccxt_config[key].get_secret_value()
    try:
        conn: CCXTExchange = getattr(ccxt.async_support, config.exchange.name)(ccxt_config)
        return conn
    except (KeyError, AttributeError) as exc:
        raise OperationalException(f"Exchange {config.exchange.name} is not supported") from exc
    except ccxt.BaseError as exc:
        raise OperationalException(f"Initialization of ccxt failed. Reason: {exc}") from exc
