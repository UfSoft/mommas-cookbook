from __future__ import annotations

import pathlib
import re
from typing import TYPE_CHECKING

import mcookbook.utils.logs

# Override python's logging handler class as soon as possible
mcookbook.utils.logs.set_logger_class()

__all__ = [
    "__version__",
    "__version_info__",
    "CODE_ROOT_DIR",
]

try:
    from .version import __version__
except ImportError:  # pragma: no cover
    __version__ = "0.0.0.not-installed"
    from importlib.metadata import version, PackageNotFoundError

    try:
        __version__ = version("mommas-cookbook")
    except PackageNotFoundError:
        # package is not installed
        pass


# Define __version_info__ attribute
VERSION_INFO_REGEX = re.compile(
    r"(?P<major>[\d]+)\.(?P<minor>[\d]+)\.(?P<patch>[\d]+)"
    r"(?:\.dev(?P<commits>[\d]+)\+g(?P<sha>[a-z0-9]+)\.d(?P<date>[\d]+))?"
)
try:
    regex_match = VERSION_INFO_REGEX.match(__version__)
    try:
        if TYPE_CHECKING:
            assert regex_match
        __version_info__ = tuple(int(p) if p.isdigit() else p for p in regex_match.groups() if p)
    finally:
        del regex_match
except AttributeError:  # pragma: no cover
    __version_info__ = (-1, -1, -1)
finally:
    del VERSION_INFO_REGEX


# Define some constants
CODE_ROOT_DIR = pathlib.Path(__file__).resolve().parent
