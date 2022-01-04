"""
Configuration related types.
"""
from __future__ import annotations

import json
import logging
import pathlib
import pprint
import traceback
from typing import Any
from typing import Optional
from typing import TypeVar

import ccxt.async_support as ccxt_async
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import validator

from mcookbook.exceptions import MCookBookSystemExit
from mcookbook.types import MCookBookBaseModel
from mcookbook.utils import merge_dictionaries
from mcookbook.utils.logs import SORTED_LEVEL_NAMES

log = logging.getLogger(__name__)

BaseConfigType = TypeVar("BaseConfigType", bound="BaseConfig")


class LoggingCliConfig(MCookBookBaseModel):
    """
    CLI logging configuration model.
    """

    level: str = "info"
    datefmt: str = "%H:%M:%S"
    fmt: str = "[%(asctime)s] [%(levelname)-7s] %(message)s"

    @validator("level")
    @classmethod
    def _validate_level(cls, value: str) -> str:
        value = value.lower()
        if value.lower() not in SORTED_LEVEL_NAMES:
            raise ValueError(
                f"The log level {value!r} is not value. Available levels: {', '.join(SORTED_LEVEL_NAMES)}"
            )
        return value


class LoggingFileConfig(MCookBookBaseModel):
    """
    Log file logging configuration model.
    """

    level: str = "info"
    datefmt: str = "%Y-%m-%d %H:%M:%S"
    fmt: str = "%(asctime)s,%(msecs)03d [%(name)-17s:%(lineno)-4d][%(levelname)-7s] %(message)s"
    path: Optional[pathlib.Path] = None

    @validator("level")
    @classmethod
    def _validate_level(cls, value: str) -> str:
        value = value.lower()
        if value.lower() not in SORTED_LEVEL_NAMES:
            raise ValueError(
                f"The log level {value!r} is not value. Available levels: {', '.join(SORTED_LEVEL_NAMES)}"
            )
        return value


class LoggingConfig(MCookBookBaseModel):
    """
    Logging configuration.
    """

    cli: LoggingCliConfig = LoggingCliConfig()
    file: LoggingFileConfig = LoggingFileConfig()


class ExchangeConfig(MCookBookBaseModel):
    """
    Exchange configuration model.
    """

    name: str
    key: str = Field(..., exclude=True)
    secret: str = Field(..., exclude=True)
    password: Optional[str] = Field(None, exclude=True)
    uid: Optional[str] = Field(None, exclude=True)
    cctx_config: Optional[dict[str, Any]] = None

    _cctx = PrivateAttr()

    @validator("name")
    @classmethod
    def _validate_exchange_name(cls, value: str) -> str:
        value = value.lower()
        ccxt_exchanges: list[str] = ccxt_async.exchanges
        if value not in ccxt_exchanges:
            raise ValueError(f"The exchange {value!r} is not supported by CCXT.")
        supported_exchanges: tuple[str, ...] = ("binance",)
        if value not in supported_exchanges:
            raise ValueError(
                f"The exchange {value!r} is not yet supported. Choose one of {', '.join(supported_exchanges)}"
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


class BaseConfig(MCookBookBaseModel):
    """
    Base configuration model.
    """

    class Config:
        """
        Schema configuration.
        """

        validate_assignment = True

    exchange: ExchangeConfig = Field(..., allow_mutation=False)

    # Optional Configs
    logging: LoggingConfig = LoggingConfig()

    # Private attributes
    _basedir: pathlib.Path = PrivateAttr()

    @classmethod
    def parse_files(cls: type[BaseConfigType], *files: pathlib.Path) -> BaseConfigType:
        """
        Helper class method to load the configuration from multiple files.
        """
        config_dicts: list[dict[str, Any]] = []
        for file in files:
            config_dicts.append(json.loads(file.read_text()))
        config = config_dicts.pop(0)
        if config_dicts:
            merge_dictionaries(config, *config_dicts)
        try:
            return cls.parse_raw(json.dumps(config))
        except Exception:
            raise MCookBookSystemExit(
                f"Failed to load configuration files:\n{traceback.format_exc()}\n\n"
                f"Merged dictionary:\n{pprint.pformat(config)}"
            )

    @property
    def basedir(self) -> pathlib.Path:
        """
        Return the base directory.
        """
        return self._basedir


class LiveConfig(BaseConfig):
    """
    Live configuration schema.
    """
