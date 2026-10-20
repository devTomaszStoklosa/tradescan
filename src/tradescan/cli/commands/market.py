"""`tradescan market`: the market regime, the benchmark's trend and the breadth."""

from __future__ import annotations

import argparse

from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.services.market import MarketRequest


def add_arguments(parser: argparse.ArgumentParser) -> None:
    arguments.add_universe_args(parser)
    arguments.add_data_args(parser)
    parser.add_argument("--benchmark")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = inputs.universe(args)
    output.loading(report, len(universe.tickers) + 1, args.period or settings.data.period)
    result = wiring.use_cases(settings, args).market.run(
        MarketRequest(universe=universe, benchmark=args.benchmark, period=args.period, interval=args.interval)
    )
    output.missing(report, result.missing)
    report.regime(result.regime)
    return 0


COMMAND = Command(
    name="market", help="market regime: benchmark trend and breadth", add_arguments=add_arguments, run=run
)
