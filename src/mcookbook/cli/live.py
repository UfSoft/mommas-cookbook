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
        self.exchange = Exchange.resolved(config)

    async def work(self) -> None:
        """
        Routines to run the service.
        """
        assert self.exchange.api  # Load cctx api
        await self.exchange.get_markets()
        await self.exchange.pairlist_manager.refresh_pairlist()
        while True:
            await asyncio.sleep(1)

    async def await_closed(self) -> None:
        """
        Run shutdown routines.
        """
        if self.exchange:
            await self.exchange.api.close()
        return await super().await_closed()


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


def post_process_argparse_parsed_args(
    parser: argparse.ArgumentParser, args: argparse.Namespace, config: LiveConfig
) -> None:
    """
    Post process the parser arguments after the configuration files have been loaded.
    """
