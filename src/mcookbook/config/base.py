"""
Base configuration schemas.
"""
from __future__ import annotations

import json
import pathlib
import pprint
import traceback
from typing import Any
from typing import TypeVar

from pydantic import BaseModel
from pydantic import Field
from pydantic import PrivateAttr

from mcookbook.config.exchange import ExchangeConfig
from mcookbook.config.logging import LoggingConfig
from mcookbook.exceptions import MCookBookSystemExit
from mcookbook.utils import merge_dictionaries

BaseConfigType = TypeVar("BaseConfigType", bound="BaseConfig")


class BaseConfig(BaseModel):
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
        except Exception as exc:
            raise MCookBookSystemExit(
                f"Failed to load configuration files:\n{traceback.format_exc()}\n\n"
                f"Merged dictionary:\n{pprint.pformat(config)}"
            ) from exc

    @property
    def basedir(self) -> pathlib.Path:
        """
        Return the base directory.
        """
        return self._basedir
