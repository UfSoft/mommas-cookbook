"""
Live trading service.
"""
from __future__ import annotations

import argparse
import asyncio

from mcookbook.cli.abc import CLIService
from mcookbook.config.live import LiveConfig
from mcookbook.exchanges import Exchange


class LiveService(CLIService):
    """
    Live trading service implementation.
    """

    def __init__(self, config: LiveConfig) -> None:
        self.config = config
        exchange_cls: type[Exchange] = Exchange.resolve(
            self.config.exchange.name, self.config.exchange.market
        )

        self.exchange = exchange_cls.construct(config=config)
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
