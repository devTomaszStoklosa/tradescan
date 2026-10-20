"""`tradescan update-universes`: refresh the index watchlists from Wikipedia."""

from __future__ import annotations

import argparse
from pathlib import Path

from tradescan.cli import inputs
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.universes import SOURCES, update_universe


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--only", help=f"comma separated: {', '.join(source.name for source in SOURCES)}")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    wanted = set(inputs.split(args.only))
    unknown = wanted - {source.name for source in SOURCES}
    if unknown:
        raise ValueError(
            f"Unknown universe(s): {', '.join(sorted(unknown))}. Use: {', '.join(s.name for s in SOURCES)}"
        )
    failures = 0
    for source in SOURCES:
        if wanted and source.name not in wanted:
            continue
        try:
            result = update_universe(source, Path(args.watchlists_dir))
        except (OSError, ValueError) as error:
            failures += 1
            report.warning(f"{source.title}: not updated, the existing file is kept ({error})")
            continue
        if result.created:
            changes = "created"
        elif result.added or result.removed:
            changes = f"+{len(result.added)} / -{len(result.removed)}"
        else:
            changes = "no changes"
        report.note(f"{source.title}: {len(result.tickers)} tickers -> {result.path} ({changes})")
        if result.added:
            report.note(f"  added: {', '.join(result.added)}")
        if result.removed:
            report.note(f"  removed: {', '.join(result.removed)}")
    return 1 if failures else 0


COMMAND = Command(
    name="update-universes",
    help="refresh the S&P 500 and Nasdaq-100 watchlists from Wikipedia",
    add_arguments=add_arguments,
    run=run,
)
