"""
Logging related utilities.
"""
from __future__ import annotations

import logging
import pathlib
import sys
from collections import deque
from collections.abc import Mapping
from datetime import datetime
from datetime import timedelta
from logging import handlers
from types import TracebackType
from typing import Any
from typing import cast
from typing import Deque
from typing import TYPE_CHECKING
from typing import Union

from cachetools import TLRUCache  # type: ignore[attr-defined]


LOG_LEVELS = {
    "all": logging.NOTSET,
    "debug": logging.DEBUG,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "quiet": 1000,
}
SORTED_LEVEL_NAMES = [lvl[0] for lvl in sorted(LOG_LEVELS.items(), key=lambda x: x[1])]

logging.root.setLevel(logging.DEBUG)

# Store an instance of the current logging logger class
LOGGING_LOGGER_CLASS: type[logging.Logger] = logging.getLoggerClass()

_ArgsType = Union[tuple[object, ...], Mapping[str, object]]
_SysExcInfoType = Union[tuple[type, BaseException, TracebackType], tuple[None, None, None]]


class LogRecord(logging.LogRecord):
    """
    Custom LogRecord implementation.
    """

    wipe_line: bool
    once_every_secs: int = 0


class TTLFilter(logging.Filter):
    """
    TTL filter in order not to spam logging it the log record has the ``once_every_secs`` attribute set.
    """

    def __init__(self, name: str = "") -> None:
        super().__init__(name=name)
        self._cache = TLRUCache(
            maxsize=10000, ttu=self._calculate_cache_time_to_use, timer=datetime.now
        )

    def _calculate_cache_time_to_use(  # pylint: disable=unused-argument
        self,
        key: int,
        record: logging.LogRecord,
        now: datetime,
    ) -> datetime:
        return now + timedelta(seconds=cast(LogRecord, record).once_every_secs)

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Determine if the specified record is to be logged.

        Returns True if the record should be logged, or False otherwise.
        If deemed appropriate, the record may be modified in-place.
        """
        try:
            if not super().filter(record):
                # Record should be filtered
                return False

            # Don't cache debug or lower log messages
            if record.levelno <= logging.DEBUG:
                return True

            # Should we consider caching the log record
            if not cast(LogRecord, record).once_every_secs:
                # No, just log it
                return True

            # Construct a cache key, based on specific log record attributes
            interesting_keys = (
                "name",
                "msg",
                "args",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
            )
            record_hash_tuple = ((key, getattr(record, key)) for key in interesting_keys)
            record_hash = hash(record_hash_tuple)
            if record_hash in self._cache:
                # Log record already in cache, don't log it again
                return False

            # First time seeing this log record, add it to cache
            self._cache[record_hash] = record
            # Log it
            return True
        finally:
            # Cleanup expired cached entries
            self._cache.expire()


class TemporaryLoggingHandler(logging.NullHandler):
    """
    Temporary logging handler, to use while logging is not setup.

    This logging handler will store all the log records up to its maximum
    queue size at which stage the first messages stored will be dropped.
    Should only be used as a temporary logging handler, while the logging
    system is not fully configured.
    Once configured, pass any logging handlers that should have received the
    initial log messages to the function
    :func:`TemporaryLoggingHandler.sync_with_handlers` and all stored log
    records will be dispatched to the provided handlers.
    """

    def __init__(self, level: int = logging.NOTSET, max_queue_size: int = 10000) -> None:
        self.__max_queue_size: int = max_queue_size
        super().__init__(level=level)
        self.__messages: Deque[logging.LogRecord] = deque(maxlen=max_queue_size)

    def handle(self, record: logging.LogRecord) -> bool:
        """
        Add ``LogRecord`` to the messages deque.
        """
        self.acquire()
        self.__messages.append(record)
        self.release()
        return True

    def sync_with_handlers(self, _handlers: list[logging.Handler] | None = None) -> None:
        """
        Sync the stored log records to the provided log handlers.
        """
        if not _handlers:
            return

        while self.__messages:
            record = self.__messages.popleft()
            for handler in _handlers:
                if handler.level > record.levelno:
                    # If the handler's level is higher than the log record one,
                    # it should not handle the log record
                    continue
                handler.handle(record)


LOGGING_TEMP_HANDLER = TemporaryLoggingHandler(logging.WARNING)


class ConsoleHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """
    Console logging handler.
    """

    _previous_record_wiped: bool = False

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the ``LogRecord``.
        """
        msg = super().format(record)
        previous_record_wiped = self._previous_record_wiped
        wipe_line = cast(LogRecord, record).wipe_line
        self._previous_record_wiped = wipe_line
        if wipe_line and previous_record_wiped:
            msg = f"\r{msg}"
        elif previous_record_wiped:
            msg = f"\n{msg}"
        return msg

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a record.

        If a formatter is specified, it is used to format the record.
        The record is then written to the stream with a trailing newline.  If
        exception information is present, it is formatted using
        traceback.print_exception and appended to the stream.  If the stream
        has an 'encoding' attribute, it is used to determine how to do the
        output to the stream.
        """
        try:
            msg: str = self.format(record)
            stream = self.stream
            # issue 35046: merged two stream.writes into one.
            if cast(LogRecord, record).wipe_line is False:
                msg = f"{msg}{self.terminator}"
            stream.write(msg)
            self.flush()
        except RecursionError:  # See issue 36272
            raise
        except Exception:  # # pylint: disable=broad-except
            self.handleError(record)


class MCookBookLoggingClass(LOGGING_LOGGER_CLASS):  # type: ignore[valid-type,misc]
    """
    Custom logging logger class implementation.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.addFilter(TTLFilter())

    def _log(
        self,
        level: int,
        msg: object,
        args: _ArgsType,
        exc_info: _SysExcInfoType | None = None,
        extra: dict[str, object] | None = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        wipe_line: bool = False,
        once_every_secs: int = 0,
    ) -> None:
        if extra is None:
            extra = {}

        extra["wipe_line"] = wipe_line
        extra["once_every_secs"] = once_every_secs

        super()._log(
            level,
            msg,
            args,
            exc_info=exc_info,
            extra=extra,
            stack_info=stack_info,
            stacklevel=stacklevel,
        )

    def makeRecord(
        self,
        name: str,
        level: int,
        fn: str,
        lno: int,
        msg: object,
        args: _ArgsType,
        exc_info: _SysExcInfoType,
        func: str | None = None,
        extra: dict[str, object] | None = None,
        sinfo: str | None = None,
    ) -> LogRecord:
        """
        Create a ``LogRecord`` instance.
        """
        if TYPE_CHECKING:
            assert extra
        # Let's remove wipe_line from extra
        wipe_line = extra.pop("wipe_line")
        # Let's remove once_every_secs from extra
        once_every_secs = extra.pop("once_every_secs")

        if not extra:
            # If nothing else is in extra, make it None
            extra = None

        logrecord: LogRecord = super().makeRecord(
            name,
            level,
            fn,
            lno,
            msg,
            args,
            exc_info,
            func=func,
            extra=extra,
            sinfo=sinfo,
        )
        setattr(logrecord, "wipe_line", wipe_line)
        setattr(logrecord, "once_every_secs", once_every_secs)
        return logrecord


def set_logger_class() -> None:
    """
    Override python's logging logger class. This should be called as soon as possible.
    """
    if logging.getLoggerClass() is not MCookBookLoggingClass:

        logging.setLoggerClass(MCookBookLoggingClass)
        logging.setLogRecordFactory(LogRecord)

        logging.root.addHandler(LOGGING_TEMP_HANDLER)


def reset_logging_handlers() -> None:
    """
    Remove any logging handlers attached to python's root logger.
    """
    for handler in list(logging.root.handlers):
        logging.root.removeHandler(handler)


def setup_cli_logging(
    log_level: str,
    fmt: str | None = None,
    datefmt: str | None = None,
) -> None:
    """
    Setup CLI logging.

    Should be called before ``setup_logfile_logging``
    """
    if fmt is None:
        fmt = "[%(asctime)s][%(levelname)-7s] - %(message)s"
    if datefmt is None:
        datefmt = "%H:%M:%S"

    reset_logging_handlers()

    handler_fmt = logging.Formatter(fmt=fmt, datefmt=datefmt)
    handler = ConsoleHandler(stream=sys.stderr)
    handler.setLevel(level=LOG_LEVELS.get(log_level) or logging.WARNING)
    handler.setFormatter(handler_fmt)
    logging.root.addHandler(handler)

    LOGGING_TEMP_HANDLER.sync_with_handlers(logging.root.handlers)


def setup_logfile_logging(
    logfile: str | pathlib.Path,
    log_level: str,
    fmt: str | None = None,
    datefmt: str | None = None,
) -> None:
    """
    Setup log file logging.

    Should be called after ``setup_logfile_logging``
    """
    if fmt is None:
        fmt = "%(asctime)s,%(msecs)03d [%(name)-17s:%(lineno)-4d][%(levelname)-7s] %(message)s"
    if datefmt is None:
        datefmt = "%Y-%m-%d %H:%M:%S"
    handler_fmt = logging.Formatter(fmt=fmt, datefmt=datefmt)
    handler = handlers.WatchedFileHandler(logfile, mode="a", encoding="utf-8", delay=False)
    handler.setLevel(level=LOG_LEVELS.get(log_level) or logging.WARNING)
    handler.setFormatter(handler_fmt)
    logging.root.addHandler(handler)
