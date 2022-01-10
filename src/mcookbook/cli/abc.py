"""
CLI related abstract classes.
"""
# pylint: disable=no-member,not-an-iterable,unsubscriptable-object
from __future__ import annotations

import abc
import argparse
import asyncio
import logging
import signal
import sys
from typing import Any

import attrs

from mcookbook.config.base import BaseConfig
from mcookbook.events import Events

log = logging.getLogger(__name__)


@attrs.define(kw_only=True)
class CLIService(abc.ABC):
    """
    CLI service abstract class.
    """

    events: Events = attrs.field()

    def __attrs_post_init__(self) -> None:
        """
        Post attrs, initialization routines.
        """
        self.events.on_stop.register(self.await_closed)

    def _on_signal(self, signum: int, _sigframe: Any) -> None:
        signal.signal(signum, signal.SIG_IGN)
        # Ignore the signal, since we've handled it already
        if signum == signal.SIGINT:
            signame = "SIGINT"
        else:
            signame = "SIGTERM"
        log.info("Caught %s signal. Terminating.", signame)
        sys.exit(0)

    def _setup_signals(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, self._on_signal)

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        """
        Setup the sub-parser.
        """

    @staticmethod
    def post_process_argparse_parsed_args(  # pylint: disable=unused-argument
        parser: argparse.ArgumentParser,
        args: argparse.Namespace,
        config: BaseConfig,
    ) -> None:
        """
        Post process the parser arguments after the configuration files have been loaded.
        """

    async def run(self) -> None:
        """
        Runs the CLI service.
        """
        self._setup_signals()
        log.info("%s is starting...", self.__class__.__name__)
        try:
            await self.events.on_start.emit()
            await self.work()
        finally:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.shield(asyncio.gather(*tasks))
            await asyncio.shield(self.events.on_stop.emit())
            log.info("%s terminated.", self.__class__.__name__)

    @abc.abstractmethod
    async def work(self) -> None:
        """
        This method must be implemented on subclasses. It's where the actual running work is done.
        """
        raise NotImplementedError

    async def await_closed(self) -> None:
        """
        Implement this method to run any async tasks on termination.
        """
