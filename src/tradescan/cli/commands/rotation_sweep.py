"""`tradescan rotation-sweep`: one or two rotation parameters over a range, in-sample and out-of-sample."""

from __future__ import annotations

import argparse

from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import FEW_TRADES, rotation_sweep_cells_frame, rotation_sweep_to_frame
from tradescan.services.rotation_sweep import RotationSweepRequest


def add_arguments(parser: argparse.ArgumentParser) -> None:
    arguments.add_universe_args(parser)
    arguments.add_data_args(parser)
    arguments.add_rotation_setup_args(parser)
    parser.add_argument("--axis", action="append", required=True, help=arguments.ROTATION_AXIS_HELP)
    parser.add_argument(
        "--metric", choices=arguments.METRIC_CHOICES, default="sharpe", help="metric shown in the grids"
    )
    parser.add_argument(
        "--export", help="save every combination with both periods' metrics and rotation stats to .csv or .json"
    )


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = inputs.universe(args)
    output.loading(report, len(universe.tickers), args.period or settings.backtest.period)
    axes = tuple(inputs.rotation_axis(text) for text in args.axis)
    result = wiring.use_cases(settings, args).rotation_sweep.run(
        RotationSweepRequest(setup=inputs.rotation_request(args, universe, ()), axes=axes)
    )
    output.missing(report, result.missing)
    base, split = result.base, result.split
    names = " x ".join(f"{item.axis.name} ({item.spec.label})" for item in result.parameters)
    report.note(
        f"{len(result.cells)} combinations of {names} on the top {base.rotation.holdings} of {universe.name}, "
        f"rebalanced {base.rotation.rebalance.value}, vectorized engine. Ranking: {base.ranking.describe()}. "
        f"Weights: {base.weighting.describe()}"
    )
    caption = f"{args.metric}; * fewer than {FEW_TRADES} trades; each period with fresh equity"
    for out_of_sample, (start, end) in ((False, split.in_sample), (True, split.out_of_sample)):
        label = f"Out-of-sample (last {split.oos_pct:g}%)" if out_of_sample else "In-sample"
        report.frame(
            rotation_sweep_to_frame(result, args.metric, out_of_sample),
            title=f"{label}, {start.date()} to {end.date()}",
            caption=caption,
            show_index=True,
        )
    errors = [cell for cell in result.cells if cell.error]
    if errors:
        report.warning(f"{len(errors)} combination(s) could not run, e.g. {errors[0].error}")
    output.export(report, rotation_sweep_cells_frame(result), args.export)
    return 0


COMMAND = Command(
    name="rotation-sweep",
    help="run a rotation over a range of one or two of its parameters, in-sample and out-of-sample",
    add_arguments=add_arguments,
    run=run,
)
