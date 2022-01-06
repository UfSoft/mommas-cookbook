"""
Exchange configuration schema.
"""
from __future__ import annotations

from typing import Any
from typing import Optional

import ccxt.async_support
from pydantic import BaseModel
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import SecretStr
from pydantic import validator


class ExchangeConfig(BaseModel):
    """
    Exchange configuration model.
    """

    name: str
    market: str = "future"
    key: Optional[SecretStr] = None
    secret: Optional[SecretStr] = None
    password: Optional[SecretStr] = None
    uid: Optional[SecretStr] = None
    cctx_config: dict[str, Any] = Field(default_factory=dict)
    pair_allow_list: list[str] = Field(default_factory=list)
    pair_block_list: list[str] = Field(default_factory=list)

    _cctx = PrivateAttr()

    @validator("name")
    @classmethod
    def _validate_exchange_name(cls, value: str) -> str:
        # Late import to avoid circular imports issue
        from mcookbook.exchanges import Exchange  # pylint: disable=import-outside-toplevel

        value = value.lower()
        ccxt_exchanges: list[str] = ccxt.async_support.exchanges
        if value not in ccxt_exchanges:
            raise ValueError(f"The exchange {value!r} is not supported by CCXT.")
        supported_exchanges: list[str] = [
            ex._name for ex in Exchange.__subclasses__()  # pylint: disable=protected-access
        ]
        if value not in supported_exchanges:
            raise ValueError(
                f"The exchange {value!r} is not yet supported. Choose one of {', '.join(supported_exchanges)}"
            )
        return value

    @validator("market")
    @classmethod
    def _validate_market(cls, value: str) -> str:
        value = value.lower()
        valid_markets: tuple[str, ...] = ("future", "spot")
        if value not in valid_markets:
            raise ValueError(
                f"The market value {value!r} is not valid. Choose one of {', '.join(valid_markets)}"
            )
        return value

    def get_ccxt_config(self) -> dict[str, Any]:
        """
        Return a dictionary which will be used to instantiate a ccxt exchange class.
        """
        ex_config = {}
        if self.key:
            ex_config["apiKey"] = self.key
        if self.secret:
            ex_config["secret"] = self.secret
        if self.password:
            ex_config["password"] = self.password
        if self.uid:
            ex_config["uid"] = self.uid
        if self.cctx_config:
            ex_config.update(self.cctx_config)
        return ex_config
