"""
Live trading service.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shlex
import shutil
from typing import TYPE_CHECKING

from mcookbook import CODE_ROOT_DIR
from mcookbook.cli.abc import CLIService
from mcookbook.config.notebook import NotebookConfig

JUPYTER_LAB_BINARY_PATH = shutil.which("jupyter-lab")

AVAILABLE_NOTEBOOKS = [
    p.stem for p in CODE_ROOT_DIR.joinpath("notebooks").glob("*.py") if not p.stem == "abc"
]

log = logging.getLogger(__name__)


class NotebookService(CLIService):
    """
    Live trading service implementation.
    """

    def __init__(self, config: NotebookConfig) -> None:
        self.config = config
        tmp_path = self.config.basedir / "tmp"
        tmp_path.mkdir(exist_ok=True)
        self.temp_notebook_path = tmp_path / self.config.notebook.name

    async def work(self) -> None:
        """
        Routines to run the service.
        """
        if TYPE_CHECKING:
            assert JUPYTER_LAB_BINARY_PATH
        if self.temp_notebook_path.exists():
            try:
                relpath = self.temp_notebook_path.relative_to(self.config.basedir)
            except ValueError:
                relpath = self.temp_notebook_path
            ret = input(f"The temporary notebook {relpath} exists, delete it? [Y/n] ")
            if ret.lower() in ("y", "ye", "yes", ""):
                self.temp_notebook_path.unlink()
        if not self.temp_notebook_path.exists():
            try:
                relsource = self.config.notebook.relative_to(self.config.basedir)
            except ValueError:
                relsource = self.config.notebook
            try:
                reldest = self.temp_notebook_path.relative_to(self.config.basedir)
            except ValueError:
                reldest = self.temp_notebook_path
            log.info("Copying %s to %s", relsource, reldest)
            shutil.copyfile(self.config.notebook, self.temp_notebook_path)
        cmd = shlex.join(
            [
                JUPYTER_LAB_BINARY_PATH,
                "-y",
                "--notebook-dir",
                str(self.config.basedir),
                str(self.temp_notebook_path),
            ]
        )
        log.info("Running: %s", cmd)
        environ = os.environ.copy()
        environ["MCB_CONFIG_FILES"] = json.dumps([str(p) for p in self.config.config_files])
        proc = await asyncio.create_subprocess_shell(cmd, env=environ)
        try:
            await proc.communicate()
        finally:
            proc.terminate()

    async def await_closed(self) -> None:
        """
        Run shutdown routines.
        """
        if self.temp_notebook_path.exists() and self.config.keep_temp_notebook is False:
            try:
                relpath = self.temp_notebook_path.relative_to(self.config.basedir)
            except ValueError:
                relpath = self.temp_notebook_path
            log.info("Deleting %s", relpath)
            self.temp_notebook_path.unlink()
        return await super().await_closed()


async def _main(config: NotebookConfig) -> None:
    """
    Asynchronous main method.
    """
    service = NotebookService(config)
    await service.run()


def main(config: NotebookConfig) -> None:
    """
    Synchronous main method.
    """
    asyncio.run(_main(config))


def setup_parser(parser: argparse.ArgumentParser) -> None:
    """
    Setup the sub-parser.
    """
    parser.add_argument("NOTEBOOK")
    parser.add_argument(
        "--keep-temp-notebook",
        action="store_true",
        default=False,
        help="Keep the temporary notebooks copied from source",
    )
    parser.set_defaults(func=main)


def post_process_argparse_parsed_args(
    parser: argparse.ArgumentParser, args: argparse.Namespace, config: NotebookConfig
) -> None:
    """
    Post process the parser arguments after the configuration files have been loaded.
    """
    if JUPYTER_LAB_BINARY_PATH is None:
        message = (
            "The pappermill library is not installed. Please run the following on your "
            "cloned repository root:\n"
            "  python -m pip install -e .[notebook]\n"
        )
        parser.exit(status=1, message=message)
    config._notebook = args.NOTEBOOK
    config._config_files = args.config_files
    config.keep_temp_notebook = args.keep_temp_notebook
