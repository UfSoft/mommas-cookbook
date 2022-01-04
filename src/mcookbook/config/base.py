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
from pydantic import validator

from mcookbook.config.exchange import ExchangeConfig
from mcookbook.config.logging import LoggingConfig
from mcookbook.exceptions import MCookBookSystemExit
from mcookbook.pairlist import PairList
from mcookbook.utils import merge_dictionaries
from mcookbook.utils import sanitize_dictionary

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
    pairlists: list[PairList] = Field(min_items=1)
    pairlist_refresh_period: int = 3600

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
        cls.update_forward_refs()
        try:
            return cls.parse_raw(json.dumps(config))
        except Exception as exc:
            raise MCookBookSystemExit(
                f"Failed to load configuration files:\n{traceback.format_exc()}\n\n"
                "Merged dictionary:\n"
                f'{pprint.pformat(sanitize_dictionary(config, ("key", "secret", "password", "uid")))}'
            ) from exc

    @validator("pairlists", each_item=True, pre=True)
    @classmethod
    def _resolve_pairlist_implementation(cls, value: dict[str, Any]) -> PairList:
        return PairList.resolved(value)

    @validator("pairlists")
    @classmethod
    def _set_pairlist_position(cls, value: list[PairList]) -> list[PairList]:
        for idx, pairlist in enumerate(value):
            pairlist._position = idx
        return value

    @property
    def basedir(self) -> pathlib.Path:
        """
        Return the base directory.
        """
        return self._basedir
