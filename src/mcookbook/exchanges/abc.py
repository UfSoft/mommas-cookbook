"""
Base exchange class implementation.
"""
from __future__ import annotations

import logging
import pprint
from typing import Any

import ccxt
from ccxt.async_support import Exchange as CCXTExchange
from pydantic import BaseModel
from pydantic import PrivateAttr

from mcookbook.config.live import LiveConfig
from mcookbook.exceptions import OperationalException
from mcookbook.pairlist.manager import PairListManager
from mcookbook.utils import merge_dictionaries
from mcookbook.utils import sanitize_dictionary

log = logging.getLogger(__name__)


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

    def _get_ccxt_headers(self) -> dict[str, str] | None:
        return None

    def _get_ccxt_config(self) -> dict[str, Any] | None:
        return {"enableRateLimit": True}

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
            sanitized_ccxt_config = sanitize_dictionary(
                ccxt_config, ("apiKey", "secret", "password", "uid")
            )
            log.info(
                "Instantiating API for the '%s' exchange with the following configuration:\n%s",
                self.config.exchange.name,
                pprint.pformat(sanitized_ccxt_config),
            )
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
