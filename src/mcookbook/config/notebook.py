"""
Notebook configuration schema.
"""
from __future__ import annotations

import pathlib

from pydantic import PrivateAttr

from mcookbook import CODE_ROOT_DIR
from mcookbook.config.base import BaseConfig


class NotebookConfig(BaseConfig):
    """
    Notebook configuration schema.
    """

    _notebook: str = PrivateAttr()
    _config_files: list[pathlib.Path] = PrivateAttr()

    @property
    def notebook(self) -> pathlib.Path:
        """
        Return the path to the notebook.
        """
        return CODE_ROOT_DIR.joinpath("notebooks", f"{self._notebook}.ipynb")

    @property
    def config_files(self) -> list[pathlib.Path]:
        """
        Return the list of the configuration files.
        """
        return list(self._config_files)
