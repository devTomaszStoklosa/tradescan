"""`tradescan sweep`: one or two parameters over a range, in-sample and out-of-sample."""

from __future__ import annotations

import argparse

from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import FEW_TRADES, sweep_cells_frame, sweep_to_frame
from tradescan.services.sweep import SweepRequest


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ticker")
    arguments.add_backtest_setup_args(parser)
    parser.add_argument("--axis", action="append", required=True, help=arguments.AXIS_HELP)
    parser.add_argument(
        "--metric", choices=arguments.METRIC_CHOICES, default="sharpe", help="metric shown in the grids"
    )
    parser.add_argument("--export", help="save every combination with both periods' metrics to .csv or .json")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    output.loading(report, 1, args.period or settings.backtest.period)
    axes = tuple(inputs.axis(text) for text in args.axis)
    result = wiring.use_cases(settings, args).sweep.run(
        SweepRequest(setup=inputs.backtest_request(args, args.ticker, ()), axes=axes)
    )
    signal, split = result.base.signal, result.split
    names = " x ".join(f"{item.axis.name} ({item.spec.label})" for item in result.parameters)
    report.note(
        f"{len(result.cells)} combinations of {names} on {result.ticker} {signal.name} ({signal.direction.value}), "
        "vectorized engine"
    )
    caption = f"{args.metric}; * fewer than {FEW_TRADES} trades"
    for out_of_sample, (start, end) in ((False, split.in_sample), (True, split.out_of_sample)):
        label = f"Out-of-sample (last {split.oos_pct:g}%)" if out_of_sample else "In-sample"
        report.frame(
            sweep_to_frame(result, args.metric, out_of_sample),
            title=f"{label}, {start.date()} to {end.date()}",
            caption=caption,
            show_index=True,
        )
    errors = [cell for cell in result.cells if cell.error]
    if errors:
        report.warning(f"{len(errors)} combination(s) could not run, e.g. {errors[0].error}")
    output.export(report, sweep_cells_frame(result), args.export)
    return 0


COMMAND = Command(
    name="sweep",
    help="backtest one or two parameters over a range, in-sample and out-of-sample",
    add_arguments=add_arguments,
    run=run,
)
