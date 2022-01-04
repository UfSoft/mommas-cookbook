"""
Live trading service.
"""
from __future__ import annotations

import argparse
import asyncio

from mcookbook.abc.cli import CLIService
from mcookbook.types.config import LiveConfig
from mcookbook.types.exchange import Exchange


class LiveService(CLIService):
    """
    Live trading service implementation.
    """

    def __init__(self, config: LiveConfig) -> None:
        self.config = config
        self.exchange: Exchange = Exchange.construct(config=config)
        print(123, self.exchange.api)

    async def work(self) -> None:
        """
        Routines to run the service.
        """
        while True:
            await asyncio.sleep(1)


async def _main(config: LiveConfig) -> None:
    """
    Asynchronous main method.
    """
    service = LiveService(config)
    await service.run()


def main(config: LiveConfig) -> None:
    """
    Synchronous main method.
    """
    asyncio.run(_main(config))


def setup_parser(parser: argparse.ArgumentParser) -> None:
    """
    Setup the sub-parser.
    """
    parser.set_defaults(func=main)
