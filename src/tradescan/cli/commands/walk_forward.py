"""`tradescan walk-forward`: re-tune on rolling windows, trade each pick next."""

from __future__ import annotations

import argparse
import math
from dataclasses import replace

from tradescan.backtest.walk_forward import DEFAULT_SELECTION_METRIC, SELECTION_METRICS, WindowScheme
from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import (
    trades_to_frame,
    walk_forward_export_frame,
    walk_forward_metrics_frame,
    walk_forward_pick,
    walk_forward_windows_frame,
)
from tradescan.services.walk_forward import WalkForwardRequest


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ticker")
    arguments.add_backtest_setup_args(parser)
    parser.add_argument("--axis", action="append", required=True, help=arguments.AXIS_HELP)
    parser.add_argument("--windows", type=int, help="out-of-sample windows (2-20, default 5)")
    parser.add_argument(
        "--in-sample-ratio",
        type=float,
        help="each in-sample window is this many times as long as an out-of-sample one (default 3)",
    )
    parser.add_argument(
        "--scheme",
        choices=[scheme.value for scheme in WindowScheme],
        default=WindowScheme.ROLLING.value,
        help="rolling: in-sample windows of fixed length; anchored: in-sample windows from the first bar",
    )
    parser.add_argument(
        "--min-trades", type=int, help="closed in-sample trades a setting needs to be picked (default 10)"
    )
    parser.add_argument(
        "--metric",
        choices=SELECTION_METRICS,
        default=DEFAULT_SELECTION_METRIC,
        help="metric each in-sample window picks by",
    )
    parser.add_argument("--trades", type=int, default=10, help="recent out-of-sample trades to show")
    parser.add_argument("--export", help="save every window with its pick and both periods' metrics to .csv or .json")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    if args.oos is not None:
        raise ValueError(
            "--oos sets a backtest's out-of-sample share; a walk-forward's windows split the history "
            "(--windows, --in-sample-ratio)"
        )
    output.loading(report, 1, args.period or settings.backtest.period)
    setup = inputs.backtest_request(args, args.ticker, ())
    windows = inputs.overrides(
        {
            "walk_forward": {
                "windows": args.windows,
                "in_sample_ratio": args.in_sample_ratio,
                "min_trades": args.min_trades,
            }
        }
    )
    request = WalkForwardRequest(
        setup=replace(setup, settings={**setup.settings, **windows}),
        axes=tuple(inputs.axis(text) for text in args.axis),
        scheme=WindowScheme(args.scheme),
        metric=args.metric,
    )
    result = wiring.use_cases(settings, args).walk_forward.run(request)
    signal, plan, walk = result.base.signal, result.plan, result.settings
    first, index = plan.windows[0], result.close.index
    names = " x ".join(f"{item.axis.name} ({item.spec.label})" for item in result.parameters)
    longer = " or more" if plan.scheme is WindowScheme.ANCHORED else ""
    report.note(
        f"{len(result.combinations)} combinations of {names} on {result.ticker} "
        f"{signal.name} ({signal.direction.value}), vectorized engine: "
        f"{walk.windows} {plan.scheme.value} windows of {first.out_of_sample.bars} bars, "
        f"each after an in-sample window of {first.in_sample.bars} bars{longer}"
    )
    report.frame(
        walk_forward_windows_frame(result),
        title="Windows",
        caption=f"Each window trades its in-sample window's highest {result.metric} with at least {walk.min_trades} "
        "trades; a position open at a window's end runs to its exit, and the next window trades from there",
    )
    efficiency = "-" if math.isnan(result.efficiency) else f"{result.efficiency:.2f}"
    report.frame(
        walk_forward_metrics_frame(result),
        title=f"Stitched out-of-sample {index[plan.start].date()} to {index[-1].date()}",
        caption=f"Walk-forward efficiency {efficiency} (stitched CAGR / average in-sample CAGR of the picks); "
        "the unchanged setup trades the same bars with the values as given",
        show_index=True,
    )
    report.note(f"Next setting: {walk_forward_pick(result, result.next_pick)}")
    errors = [item for item in result.combinations if item.error]
    if errors:
        report.warning(f"{len(errors)} combination(s) could not run, e.g. {errors[0].error}")
    trades = trades_to_frame(result.stitched.trades)
    report.frame(trades.tail(args.trades), title=f"Last {args.trades} out-of-sample trades")
    output.export(report, walk_forward_export_frame(result), args.export)
    return 0


COMMAND = Command(
    name="walk-forward",
    help="re-tune one or two parameters on rolling in-sample windows and trade each pick on the next window",
    add_arguments=add_arguments,
    run=run,
)
