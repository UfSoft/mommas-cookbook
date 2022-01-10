"""
Pair list handlers configurations.
"""
from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING
from typing import TypeVar

from pydantic import BaseModel
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import root_validator
from pydantic import validator

if TYPE_CHECKING:
    from mcookbook.pairlist.abc import PairList

PairListConfigType = TypeVar("PairListConfigType", bound="PairListConfig")


class PairListConfig(BaseModel):
    """
    Base pairlist configuration.
    """

    _order: int = PrivateAttr()
    _handler_name: str = PrivateAttr()
    name: str = Field(...)
    refresh_period: int = Field(default=1800, ge=0)

    def __new__(  # pylint: disable=unused-argument
        cls: type[PairListConfig], name: str, **kwargs: Any
    ) -> PairListConfig:
        """
        Override class to instantiate.

        Override __new__ so that we can switch the class with one of it's
        sub-classes before instantiating.
        """
        for subclass in cls.__subclasses__():
            if subclass._handler_name == name:
                return BaseModel.__new__(subclass)
        raise ValueError(f"Cloud not find an {name} pairlist config implementation.")

    def __init_subclass__(cls, *, handler_name: str, **kwargs: Any):
        """
        Post attrs, initialization routines.
        """
        super().__init_subclass__(**kwargs)
        cls._handler_name = handler_name

    def init_handler(self, **kwargs: Any) -> PairList:
        """
        Instantiate the pair list handler corresponding to this configuration.
        """
        from mcookbook.pairlist.abc import PairList  # pylint: disable=import-outside-toplevel

        for subclass in PairList.__subclasses__():
            if subclass.__name__ == self._handler_name:
                return subclass(**kwargs)
        raise ValueError(f"Cloud not find an {self.name} pairlist handler implementation.")


class StaticPairListConfig(PairListConfig, handler_name="StaticPairList"):
    """
    Static pair list configuration.
    """


class VolumePairListConfig(PairListConfig, handler_name="VolumePairList"):
    """
    Volume pair list configuration.
    """

    number_assets: int = Field(description="Number of assets", ge=1)
    sort_key: str = "quoteVolume"
    min_value: float = Field(default=0, ge=0.0)
    lookback_days: int = Field(0, ge=0)
    lookback_timeframe: str = "1d"
    lookback_period: int = Field(0, ge=0)

    @validator("sort_key")
    @classmethod
    def _validate_sort_key(cls, value: str) -> str:
        if value != "quoteVolume":
            raise ValueError("'sort_key' needs to be set to 'quoteVolume'.")
        return value

    @validator("lookback_period")
    @classmethod
    def _validate_lookback_period(cls, value: int, values: dict[str, Any]) -> int:
        if value > 0 and values["lookback_days"] > 0:
            raise ValueError(
                "Ambiguous configuration: lookback_days and lookback_period both set in pairlist "
                "config. Please set lookback_days only or lookback_period and lookback_timeframe "
                "and restart."
            )
        return value

    @root_validator
    @classmethod
    def _validate_configs(cls, values: dict[str, Any]) -> dict[str, Any]:
        # overwrite lookback timeframe and days when lookback_days is set
        if values["lookback_days"] > 0:
            values["lookback_timeframe"] = "1d"
            values["lookback_period"] = values["lookback_days"]
        return values
