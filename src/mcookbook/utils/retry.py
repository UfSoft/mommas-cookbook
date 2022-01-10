"""
Retry related utilities.
"""
from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any
from typing import cast
from typing import TypeVar

from mcookbook.exceptions import DDosProtection
from mcookbook.exceptions import TemporaryError

log = logging.getLogger(__name__)

FuncTypeVar = TypeVar("FuncTypeVar", bound=Callable[..., Any])

# Maximum default retry count.
# Functions are always called RETRY_COUNT + 1 times (for the original call)
API_RETRY_COUNT = 4


def calculate_backoff(retrycount: int, max_retries: int) -> int:
    """
    Calculate backoff.
    """
    return (max_retries - retrycount) ** 2 + 1


def async_retrier(func: FuncTypeVar) -> FuncTypeVar:
    """
    Retry the async function.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        count = kwargs.pop("count", API_RETRY_COUNT)
        kucoin = args[0].config.exchange.name == "Kucoin"  # Check if the exchange is KuCoin.
        try:
            return await func(*args, **kwargs)
        except TemporaryError as ex:
            msg = f'{func.__name__}() returned exception: "{ex}". '
            if count > 0:
                msg += f"Retrying still for {count} times."
                count -= 1
                kwargs["count"] = count
                if isinstance(ex, DDosProtection):
                    if kucoin and "429000" in str(ex):
                        # Temporary fix for 429000 error on kucoin
                        # see https://github.com/freqtrade/freqtrade/issues/5700 for details.
                        log.warning(  # type: ignore[call-arg]
                            "Kucoin 429 error, avoid triggering DDosProtection backoff delay. "
                            "%s tries left before giving up",
                            count,
                            once_every_secs=15,
                        )
                        # Reset msg to avoid logging too many times.
                        msg = ""
                    else:
                        backoff_delay = calculate_backoff(count + 1, API_RETRY_COUNT)
                        log.info("Applying DDosProtection backoff delay: %s", backoff_delay)
                        await asyncio.sleep(backoff_delay)
                if msg:
                    log.warning(msg)
                return await wrapper(*args, **kwargs)
            else:
                log.warning(  # pylint: disable=logging-not-lazy,logging-fstring-interpolation
                    f"{msg}Giving up."
                )
                raise ex

    return cast(FuncTypeVar, wrapper)
