"""What a subcommand of the CLI declares; `commands.COMMANDS` lists them in the order `--help` shows them."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass

from tradescan.config import Settings
from tradescan.report.console import ConsoleReport

Handler = Callable[[argparse.Namespace, Settings, ConsoleReport], int]


@dataclass(frozen=True)
class Command:
    """One subcommand: its name and help in `tradescan --help`, the arguments it adds and the handler it runs."""

    name: str
    help: str
    add_arguments: Callable[[argparse.ArgumentParser], None]
    run: Handler
