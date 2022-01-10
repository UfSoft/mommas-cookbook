"""
Momma's Cookbook Exceptions.
"""
from __future__ import annotations


class MCookBookBaseException(Exception):
    """
    Base Momma's Cookbook exception.
    """


class MCookBookSystemExit(SystemExit):
    """
    Exception raised to exit.
    """


class OperationalException(MCookBookBaseException):
    """
    Operational exception.
    """


class DependencyException(MCookBookBaseException):
    """
    Indicates that an assumed dependency is not met.

    This could happen when there is currently not enough money on the account.
    """


class ExchangeError(DependencyException):
    """
    Error raised out of the exchange.

    Has multiple Errors to determine the appropriate error.
    """


class TemporaryError(ExchangeError):
    """
    Temporary network or exchange related error.

    This could happen when an exchange is congested, unavailable, or the user
    has networking problems. Usually resolves itself after a time.
    """


class DDosProtection(TemporaryError):
    """
    Temporary error caused by DDOS protection.

    Bot will wait for a second and then retry.
    """
