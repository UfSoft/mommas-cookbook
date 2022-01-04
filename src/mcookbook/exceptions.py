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
