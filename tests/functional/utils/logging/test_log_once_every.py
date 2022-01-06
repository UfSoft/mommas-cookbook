from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)


def test_no_logging_filtering(caplog):
    def log_it():
        log.debug("Just log it!")

    with caplog.at_level(logging.DEBUG, logger=__name__):
        log_it()
        log_it()
        log_it()
        log_it()
    assert len(caplog.records) == 4


def test_logging_filtering(caplog):
    def log_it(ttu: int | float = 1):
        log.info("Just log it!", once_every_secs=ttu)  # type: ignore[call-arg]

    with caplog.at_level(logging.INFO, logger=__name__):
        log_it()
        log_it()
        log_it()
    assert len(caplog.records) == 1


def test_logging_filtering_after_ttu(caplog):
    def log_it(ttu: int | float = 1):
        log.info("Just log it!", once_every_secs=ttu)  # type: ignore[call-arg]

    with caplog.at_level(logging.INFO, logger=__name__):
        log_it(ttu=0.1)
        log_it()
        time.sleep(0.15)
        log_it(ttu=0.1)
        log_it()
    assert len(caplog.records) == 2


def test_no_logging_filtering_at_debug_level(caplog):
    def log_it(ttu: int | float = 1):
        log.debug("Just log it!", once_every_secs=ttu)  # type: ignore[call-arg]

    with caplog.at_level(logging.DEBUG, logger=__name__):
        log_it()
        log_it()
        log_it()
        log_it()
    assert len(caplog.records) == 4
