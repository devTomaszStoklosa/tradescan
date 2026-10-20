"""Command line interface: parses arguments, calls the use cases in `services`, renders the reports.

Each subcommand is a module of `commands`; this module builds the parser from them and runs the one given.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from rich.console import Console

from tradescan.cli.command import Handler
from tradescan.cli.commands import COMMANDS
from tradescan.config import load_settings
from tradescan.report.console import ConsoleReport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradescan",
        description="Trading signal scanner: vectorized pandas signals on yfinance data, optional backtrader check.",
    )
    parser.add_argument("--config", default="config/settings.toml", help="settings file (TOML)")
    parser.add_argument("--watchlists-dir", default="config/watchlists")
    parser.add_argument("-v", "--verbose", action="store_true", help="show data download warnings")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        subparser = commands.add_parser(command.name, help=command.help)
        command.add_arguments(subparser)
        subparser.set_defaults(handler=command.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.verbose else logging.ERROR, format="%(levelname)s %(message)s")
    if not args.verbose:
        # Missing tickers are already reported once by the scanner; yfinance would log every failure again.
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    report = ConsoleReport(Console())
    try:
        settings = load_settings(Path(args.config))
        handler: Handler = args.handler
        return handler(args, settings, report)
    except (FileNotFoundError, KeyError, ValueError, ImportError) as error:
        message = error.args[0] if error.args else str(error)
        report.warning(f"Error: {message}")
        return 2
