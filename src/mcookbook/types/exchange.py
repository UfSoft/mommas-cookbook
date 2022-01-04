"""
Base exchange class implementation.
"""
from __future__ import annotations

import copy
import logging
import pprint
from typing import Any
from typing import Optional

import ccxt
from ccxt.async_support import Exchange as CCXTExchange
from pydantic import BaseModel
from pydantic import PrivateAttr

from mcookbook.exceptions import OperationalException
from mcookbook.types.config import LiveConfig
from mcookbook.utils import merge_dictionaries

log = logging.getLogger(__name__)


class Exchange(BaseModel):
    """
    Base Exchange class.
    """

    config: LiveConfig

    _api: type[CCXTExchange] = PrivateAttr()

    def _get_ccxt_headers(self) -> Optional[dict[str, str]]:
        return None

    def _get_ccxt_config(self) -> Optional[dict[str, Any]]:
        return None

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
            exchange_ccxt_config = self._get_ccxt_config()
            if exchange_ccxt_config:
                merge_dictionaries(ccxt_config, exchange_ccxt_config)
            headers = self._get_ccxt_headers()
            if headers:
                merge_dictionaries(ccxt_config, {"headers": headers})
            sanitized_ccxt_config = copy.deepcopy(ccxt_config)
            for key in ("apiKey", "secret", "password", "uid"):
                if key in sanitized_ccxt_config:
                    sanitized_ccxt_config[key] = "*****"
            log.info(
                "Instantiating API for the '%s' exchange with the following configuration:\n%s",
                self.config.exchange.name,
                pprint.pformat(sanitized_ccxt_config),
            )
            try:
                self._api = getattr(ccxt.async_support, self.config.exchange.name)(ccxt_config)
            except (KeyError, AttributeError) as e:
                raise OperationalException(
                    f"Exchange {self.config.exchange.name} is not supported"
                ) from e
            except ccxt.BaseError as e:
                raise OperationalException(f"Initialization of ccxt failed. Reason: {e}") from e
        return self._api
