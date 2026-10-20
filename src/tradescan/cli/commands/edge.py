"""`tradescan edge`: historical forward returns after each signal."""

from __future__ import annotations

import argparse

from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import edge_to_frame
from tradescan.services.edge import EdgeRequest


def add_arguments(parser: argparse.ArgumentParser) -> None:
    arguments.add_universe_args(parser)
    arguments.add_data_args(parser)
    arguments.add_signal_filter_args(parser)
    parser.add_argument("--horizons", default="5,10,20", help="bars after the signal, comma separated")
    parser.add_argument("--min-events", type=int, default=0, help="hide signals with fewer events")
    parser.add_argument("--export", help="save to .csv or .json")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = inputs.universe(args)
    output.loading(report, len(universe.tickers), args.period or settings.backtest.period)
    result = wiring.use_cases(settings, args).edge.run(
        EdgeRequest(
            universe=universe,
            signals=inputs.signal_filter(args),
            horizons=tuple(int(value) for value in inputs.split(args.horizons)),
            min_events=args.min_events,
            period=args.period,
            interval=args.interval,
        )
    )
    output.missing(report, result.missing)
    frame = edge_to_frame(result.rows)
    report.frame(
        frame,
        title=f"Signal edge on {universe.name} ({result.tickers} tickers)",
        caption="Returns in the signal's direction from the next open; 'vs base' = minus the average of all bars. "
        "Small N is noise; current watchlists carry survivorship bias.",
    )
    output.export(report, frame, args.export)
    return 0


COMMAND = Command(
    name="edge", help="historical forward returns after each signal", add_arguments=add_arguments, run=run
)
