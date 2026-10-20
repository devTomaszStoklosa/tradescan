"""`tradescan list-signals`: every signal with its family, direction and weight."""

from __future__ import annotations

import argparse

from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import signals_to_frame
from tradescan.services.builders import build_scorer
from tradescan.signals import default_registry


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """The command has no arguments of its own."""


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    signals = default_registry.select()
    report.frame(signals_to_frame(signals, build_scorer(settings)), title=f"{len(signals)} signals")
    return 0


COMMAND = Command(
    name="list-signals", help="show all signals with family, direction and weight", add_arguments=add_arguments, run=run
)
