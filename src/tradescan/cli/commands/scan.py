"""`tradescan scan`: fresh signals on a watchlist, scored, with a risk plan."""

from __future__ import annotations

import argparse

from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import SCAN_COLUMNS, hits_to_frame
from tradescan.services.scan import ScanRequest


def add_arguments(parser: argparse.ArgumentParser) -> None:
    arguments.add_universe_args(parser)
    arguments.add_data_args(parser)
    arguments.add_signal_filter_args(parser)
    arguments.add_account_args(parser)
    parser.add_argument("--fresh", type=int, help="signal must have fired within the last N bars")
    parser.add_argument("--min-score", type=float, help="hide setups scoring below this")
    parser.add_argument("--top", type=int, default=25, help="rows to show")
    parser.add_argument("--benchmark", help="benchmark ticker for regime (default from watchlist or settings)")
    parser.add_argument("--export", help="save all hits to .csv or .json")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = inputs.universe(args)
    output.loading(report, len(universe.tickers) + 1, args.period or settings.data.period)
    result = wiring.use_cases(settings, args).scan.run(
        ScanRequest(
            universe=universe,
            signals=inputs.signal_filter(args),
            settings=inputs.overrides(
                {"account": inputs.account(args), "scan": {"fresh_bars": args.fresh, "min_score": args.min_score}}
            ),
            benchmark=args.benchmark,
            period=args.period,
            interval=args.interval,
        )
    )
    output.missing(report, result.missing)
    report.regime(result.regime)
    if result.skipped:
        report.warning(f"Not enough history, skipped: {', '.join(result.skipped)}")
    report.frame(
        hits_to_frame(result.hits[: args.top]),
        title=f"{universe.name}: {len(result.hits)} setups (score >= {result.min_score:g})",
        columns=SCAN_COLUMNS,
        caption=f"signal(bars ago); edge = next-open entry, {result.edge_horizon}-bar outcome of the "
        "most recent signal on this ticker; not investment advice",
    )
    output.export(report, hits_to_frame(result.hits), args.export)
    return 0


COMMAND = Command(
    name="scan", help="find fresh signals, score them and plan the risk", add_arguments=add_arguments, run=run
)
