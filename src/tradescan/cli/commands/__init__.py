"""The CLI's subcommands, one module each, in the order `tradescan --help` lists them."""

from __future__ import annotations

from tradescan.cli.command import Command
from tradescan.cli.commands import (
    backtest,
    edge,
    list_signals,
    market,
    portfolio_backtest,
    rotation_backtest,
    scan,
    serve,
    sweep,
    update_universes,
    walk_forward,
    watchlist_backtest,
)

COMMANDS: tuple[Command, ...] = (
    list_signals.COMMAND,
    scan.COMMAND,
    market.COMMAND,
    edge.COMMAND,
    backtest.COMMAND,
    sweep.COMMAND,
    walk_forward.COMMAND,
    watchlist_backtest.COMMAND,
    portfolio_backtest.COMMAND,
    rotation_backtest.COMMAND,
    update_universes.COMMAND,
    serve.COMMAND,
)
