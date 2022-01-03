"""
CLI related abstract classes.
"""
from __future__ import annotations

import abc
import asyncio
import logging
import signal
import sys
from typing import Any

log = logging.getLogger(__name__)


class CLIService(metaclass=abc.ABCMeta):
    """
    CLI service abstract class.
    """

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

    async def run(self) -> None:
        """
        Runs the CLI service.
        """
        self._setup_signals()
        try:
            await self.work()
        finally:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.shield(asyncio.gather(*tasks))
            await asyncio.shield(self.await_closed())
            log.info("Passivbot terminated")

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
