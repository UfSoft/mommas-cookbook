"""
CLI entry point.
"""
from __future__ import annotations

import argparse
import logging
import multiprocessing
import pathlib
import sys
import traceback
from typing import cast

from pydantic import ValidationError

from mcookbook import __version__
from mcookbook.cli import live
from mcookbook.cli import notebook
from mcookbook.config.live import LiveConfig
from mcookbook.config.notebook import NotebookConfig
from mcookbook.exceptions import MCookBookSystemExit
from mcookbook.utils.logs import setup_cli_logging
from mcookbook.utils.logs import setup_logfile_logging
from mcookbook.utils.logs import SORTED_LEVEL_NAMES

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """
    Parse the CLI and run the command.
    """
    parser = argparse.ArgumentParser(
        prog="mommas-cookbook", description="Momma's Crypto Trading Bot"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    config_section = parser.add_argument_group(title="Configuration Paths")
    config_section.add_argument(
        "--basedir",
        type=pathlib.Path,
        default=None,
        help=(
            "The base directory where all paths will be computed from. "
            "Defaults to the current directory"
        ),
    )
    config_section.add_argument(
        "-c",
        "--config",
        "--config-file",
        type=pathlib.Path,
        dest="config_files",
        default=[],
        action="append",
        help=(
            "Path to configuration file. Can be passed multiple times, but the last configuration file "
            "will be merged into the previous one, and so forth, overriding the previously defined values."
        ),
    )
    cli_logging_params = parser.add_argument_group(
        title="Logging", description="Runtime logging configuration"
    )
    cli_logging_params.add_argument(
        "--log-level",
        choices=SORTED_LEVEL_NAMES,
        default=None,
        help="CLI logging level. Default: info",
    )
    cli_logging_params.add_argument(
        "--log-file", type=pathlib.Path, default=None, help="Path to logs file"
    )
    cli_logging_params.add_argument(
        "--log-file-level",
        choices=SORTED_LEVEL_NAMES,
        default=None,
        help="Logs file logging level. Default: info",
    )
    subparsers = parser.add_subparsers(title="Commands", dest="subparser")
    live_parser = subparsers.add_parser("live", help="Run Live")
    notebook_parser = subparsers.add_parser("notebook", help="Run a provided jupyter notebook")

    # Setup each sub-parser
    live.setup_parser(live_parser)
    notebook.setup_parser(notebook_parser)

    # Parse the CLI arguments
    args: argparse.Namespace = parser.parse_args(args=argv)

    if args.basedir is not None:
        args.basedir = args.basedir.resolve()
    else:
        args.basedir = pathlib.Path.cwd()

    for config_file in list(args.config_files):
        if not config_file.exists():
            log.warning("Config file %s does not exist", config_file)
            args.config_files.remove(config_file)

    if not args.config_files:
        default_config_file = args.basedir / "configs" / "live" / "default.json"
        if not default_config_file.exists():
            parser.exit(
                status=1,
                message=(
                    f"Please pass '--config=<path/to/config.json>' at least once or create {default_config_file}"
                ),
            )
        args.config_files.append(default_config_file)

    config: LiveConfig | NotebookConfig
    try:
        if args.subparser == "live":
            config = LiveConfig.parse_files(*args.config_files)
        elif args.subparser == "notebook":
            config = NotebookConfig.parse_files(*args.config_files)
        else:
            parser.exit(
                status=1,
                message=(
                    f"Don't know what to do regarding subparser '{args.subparser}'. Please fix this "
                    "or file a bug report."
                ),
            )
    except ValidationError as exc:
        parser.exit(status=1, message=f"Found some errors in the configuration:\n\n{exc}\n")
    except Exception:  # pylint: disable=broad-except
        parser.exit(
            status=1, message=f"Failed to load the configuration:\n{traceback.format_exc()}"
        )

    # Setup logging
    setup_cli_logging(
        log_level=args.log_level or config.logging.cli.level,
        fmt=config.logging.cli.fmt,
        datefmt=config.logging.cli.datefmt,
    )
    log_file_path: pathlib.Path | None = args.log_file or config.logging.file.path
    if log_file_path:
        setup_logfile_logging(
            logfile=log_file_path,
            log_level=args.log_file_level or config.logging.file.level,
            fmt=config.logging.file.fmt,
            datefmt=config.logging.file.datefmt,
        )

    log.info("Configuration loaded from:")
    for config_file in args.config_files:
        try:
            log.info("  - %s", config_file.relative_to(args.basedir))
        except ValueError:
            log.info("  - %s", config_file)

    # Set the configuration private attributes
    config._basedir = args.basedir  # pylint: disable=protected-access

    try:
        if args.subparser == "live":
            live.post_process_argparse_parsed_args(parser, args, cast(LiveConfig, config))
        elif args.subparser == "notebook":
            notebook.post_process_argparse_parsed_args(parser, args, cast(NotebookConfig, config))
    except AttributeError:
        # process_argparse_parsed_args was not implemented
        pass

    try:
        args.func(config)
    except MCookBookSystemExit as exc:
        parser.exit(status=1, message=f"Error: {exc}")
    except Exception:  # pylint: disable=broad-except
        parser.exit(
            status=1,
            message=f"There was an error running {args.subparser}:\n{traceback.format_exc()}",
        )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main(sys.argv)
