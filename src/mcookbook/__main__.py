"""
CLI entry point.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import multiprocessing
import pathlib
import traceback
from typing import cast
from typing import TYPE_CHECKING

from dependency_injector import containers
from dependency_injector import providers
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from pydantic import BaseModel
from pydantic import ValidationError

from mcookbook import __version__
from mcookbook.cli.notebook import NotebookService
from mcookbook.cli.trade import TradeService
from mcookbook.config.exchange import ExchangeConfig
from mcookbook.config.notebook import NotebookConfig
from mcookbook.config.trade import TradeConfig
from mcookbook.events import Events
from mcookbook.exchanges.abc import Exchange
from mcookbook.pairlist.manager import PairListManager
from mcookbook.utils.ccxt import create_ccxt_conn
from mcookbook.utils.logs import LOG_LEVELS
from mcookbook.utils.logs import setup_cli_logging
from mcookbook.utils.logs import setup_logfile_logging
from mcookbook.utils.logs import SORTED_LEVEL_NAMES

log = logging.getLogger(__name__)


class Application(containers.DeclarativeContainer):  # type: ignore[misc]
    """
    Main application dependency injector container.
    """

    events = providers.Singleton(Events)
    config = providers.Dependency(instance_of=BaseModel)
    exchange_class = providers.Singleton(
        Exchange.resolve_class,
        config=config,
    )
    ccxt_conn = providers.Singleton(
        create_ccxt_conn,
        config=config,
        exchange_class=exchange_class,
    )
    exchange = providers.Singleton(
        Exchange,
        events=events,
        config=config,
        ccxt_conn=ccxt_conn,
    )
    pairlist_manager = providers.Singleton(
        PairListManager,
        events=events,
        config=config,
        ccxt_conn=ccxt_conn,
        exchange=exchange,
    )
    trade_service = providers.Factory(
        TradeService,
        events=events,
        config=config,
        ccxt_conn=ccxt_conn,
        pairlist_manager=pairlist_manager,
    )
    notebook_service = providers.Factory(
        NotebookService,
        config=config,
    )


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
        "--bd",
        "--basedir",
        type=pathlib.Path,
        default=None,
        dest="basedir",
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
            "will be merged into the previous one, and so forth, overriding the previously defined values. "
            "Default: <current-directory>/runtime/default.json"
        ),
    )
    generate_config_group = config_section.add_mutually_exclusive_group()
    generate_config_group.add_argument(
        "--grdl",
        "--generate-runtime-directory-layout",
        dest="generate_runtime_directory_layout",
        type=pathlib.Path,
        help=(
            "Generate the runtime directory structure, including default configuration file, "
            "for the provided path."
        ),
    )
    generate_config_group.add_argument(
        "--grdl-full",
        "--generate-full-runtime-directory-layout",
        dest="generate_full_runtime_directory_layout",
        type=pathlib.Path,
        help=(
            "Generate the runtime directory structure, including full configuration file, "
            "for the provided path."
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
    trade_parser = subparsers.add_parser("trade", help="Run trading service")
    notebook_parser = subparsers.add_parser("notebook", help="Run a provided jupyter notebook")

    # Setup each sub-parser
    TradeService.setup_parser(trade_parser)
    NotebookService.setup_parser(notebook_parser)

    # Parse the CLI arguments
    args: argparse.Namespace = parser.parse_args(args=argv)

    if args.generate_runtime_directory_layout or args.generate_full_runtime_directory_layout:
        setup_cli_logging(log_level=args.log_level or "info")
        basedir: pathlib.Path
        if args.generate_full_runtime_directory_layout:
            basedir = args.generate_full_runtime_directory_layout
            exclude = None
        else:
            basedir = args.generate_runtime_directory_layout
            exclude = {
                "logging": {
                    "file": ...,
                    "cli": ...,
                },
            }
        basedir.mkdir(exist_ok=True, parents=True, mode=0o750)
        log.info("Created directory: %s", basedir)
        default_config = TradeConfig.construct(
            exchange=ExchangeConfig.construct(
                name="CHANGE_ME",
                pair_allow_list=[
                    "BTC/USDT",
                ],
            ),
            # pairlists=[
            #    StaticPairList.construct(),
            # ],
        )
        default_config_contents = default_config.json(
            indent=2,
            by_alias=True,
            exclude=exclude,  # type: ignore[arg-type]
        )
        default_config_file = basedir / "default.json"
        if default_config_file.exists():
            response = input(f"The file {default_config_file} already exists. Overwrite? [N/y] ")
            if response.lower() not in ("y", "ye", "yes"):
                parser.exit(1)
        log.info("Writing %s with contents:\n%s", default_config_file, default_config_contents)
        default_config_file.write_text(default_config_contents)
        parser.exit(
            status=0, message=f"Runtime directory structure created at {basedir.resolve()}\n"
        )

    if args.basedir is not None:
        args.basedir = args.basedir.resolve()
    else:
        args.basedir = pathlib.Path.cwd() / "runtime"

    for config_file in list(args.config_files):
        if not config_file.exists():
            log.warning("Config file %s does not exist", config_file)
            args.config_files.remove(config_file)

    if not args.config_files and args.basedir:
        default_config_file = args.basedir / "default.json"
        if not default_config_file.exists():
            parser.exit(
                status=1,
                message=(
                    "Please pass '--config=<path/to/config.json>' at least once or "
                    "--grdl/--generate-runtime-directory-layout <path/to/directory> "
                    "to create the initial directory structure and default config file."
                ),
            )
        args.config_files.append(default_config_file)

    config: TradeConfig | NotebookConfig | None = None
    try:
        if args.subparser == "trade":
            config = TradeConfig.parse_files(*args.config_files)
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

    if TYPE_CHECKING:
        assert config

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
    # Adjust specific logging handler levels
    for logger, level in config.logging.levels.dict(by_alias=True).items():
        logging.getLogger(logger).setLevel(LOG_LEVELS[level])

    log.info("Configuration loaded from:")
    for config_file in args.config_files:
        try:
            log.info("  - %s", config_file.relative_to(args.basedir))
        except ValueError:
            log.info("  - %s", config_file)

    # Set the configuration private attributes
    config._basedir = args.basedir  # pylint: disable=protected-access

    if args.subparser == "trade":
        TradeService.post_process_argparse_parsed_args(parser, args, cast(TradeConfig, config))
    elif args.subparser == "notebook":
        NotebookService.post_process_argparse_parsed_args(
            parser, args, cast(NotebookConfig, config)
        )

    app = Application(config=config)
    app.wire(modules=[__name__])
    asyncio.run(connect_services(args))


@inject  # type: ignore[misc]
async def connect_services(
    args: argparse.Namespace,
    application: Application = Provide[Application],
) -> None:
    """
    Run dependency injector wiring routines.
    """
    service: TradeService | NotebookService | None = None
    if args.subparser == "trade":
        service = application.trade_service()
    elif args.subparser == "notebook":
        service = application.notebook_service()
    if TYPE_CHECKING:
        assert service

    await service.run()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
