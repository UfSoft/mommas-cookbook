"""
Configuration related types.
"""
from __future__ import annotations

import json
import pathlib
import pprint
import traceback
from typing import Any
from typing import Optional
from typing import TypeVar

from pydantic import PrivateAttr
from pydantic import validator

from mcookbook.exceptions import MCookBookSystemExit
from mcookbook.types import MCookBookBaseModel
from mcookbook.utils.logs import SORTED_LEVEL_NAMES

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


class Exchange(MCookBookBaseModel):
    """
    Exchange configuration model.
    """

    name: str
    key: str
    secret: str

    @validator("name")
    @classmethod
    def _validate_exchange_name(cls, value: str) -> str:
        supported_exchanges: tuple[str, ...] = ("binance",)
        if value not in supported_exchanges:
            raise ValueError(
                f"The exchange {value!r} is not supported. Choose one of {', '.join(supported_exchanges)}"
            )
        return value


class BaseConfig(MCookBookBaseModel):
    """
    Base configuration model.
    """

    exchange: Exchange

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


def merge_dictionaries(target_dict: dict[Any, Any], *source_dicts: dict[Any, Any]) -> None:
    """
    Recursively merge each of the ``source_dicts`` into ``target_dict`` in-place.
    """
    for source_dict in source_dicts:
        for key, value in source_dict.items():
            if isinstance(value, dict):
                target_dict_value = target_dict.setdefault(key, {})
                merge_dictionaries(target_dict_value, value)
            else:
                target_dict[key] = value
