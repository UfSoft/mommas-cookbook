"""
Logging configuration models.
"""
from __future__ import annotations

import pathlib
from typing import Optional

from pydantic import BaseModel
from pydantic import validator

from mcookbook.utils.logs import SORTED_LEVEL_NAMES


class LoggingCliConfig(BaseModel):
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


class LoggingFileConfig(BaseModel):
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


class LoggingConfig(BaseModel):
    """
    Logging configuration.
    """

    cli: LoggingCliConfig = LoggingCliConfig()
    file: LoggingFileConfig = LoggingFileConfig()
