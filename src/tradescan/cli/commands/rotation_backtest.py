"""`tradescan rotation-backtest`: hold a watchlist's strongest tickers."""

from __future__ import annotations

import argparse

import pandas as pd

from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import contributions_frame, portfolio_trades_frame, rotation_metrics_frame, targets_frame
from tradescan.services.composition import default_rotation_engines


def add_arguments(parser: argparse.ArgumentParser) -> None:
    arguments.add_universe_args(parser)
    arguments.add_data_args(parser)
    arguments.add_rotation_setup_args(parser)
    parser.add_argument("--engine", choices=arguments.ENGINE_CHOICES, default="vectorized")
    parser.add_argument("--top", type=int, default=15, help="tickers to show, largest P&L first (0: all)")
    parser.add_argument("--export", help="save every engine's trades to .csv or .json")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = inputs.universe(args)
    output.loading(report, len(universe.tickers), args.period or settings.backtest.period)
    engines = tuple(default_rotation_engines()) if args.engine == "both" else (args.engine,)
    request = inputs.rotation_request(args, universe, engines)
    result = wiring.use_cases(settings, args).rotation.run(request)
    output.missing(report, result.missing)
    rotation, config, first = result.rotation, result.config, result.runs[0]
    defensive = rotation.safe_asset or "cash"
    check = (
        f"a pick at or below 0 over {rotation.absolute_lookback} bars goes to {defensive}"
        if rotation.checks_momentum
        else "no absolute momentum check"
    )
    tickers = sum(row.ticker in universe.tickers for row in first.contributions)
    report.note(
        f"Top {rotation.holdings} of {tickers} tickers of {universe.name}, rebalanced {rotation.rebalance.value}. "
        f"Ranking: {result.ranking.describe()}. Weights: {result.weighting.describe()}. Absolute momentum: {check}. "
        f"Costs {config.commission_pct:g}% + {config.slippage_pct:g}% slippage"
    )
    split = result.split
    dates = result.dates
    report.frame(
        rotation_metrics_frame(result),
        title=f"{universe.name} rotation, {dates[0].date()} to {dates[-1].date()}",
        caption=f"from the first rebalance with a pick; buy & hold is {result.benchmark}'s, exposure the share of days "
        "with a holding"
        + (
            f"; out-of-sample from {split.out_of_sample[0].date()} (last {split.oos_pct:g}%), "
            "each period with fresh equity"
            if split
            else ""
        ),
        show_index=True,
    )
    if split is None:
        report.warning(f"History too short for an out-of-sample split at {config.oos_pct:g}%")
    targets = result.targets
    in_safe = f"{targets.safe_pct:.1f}% in {rotation.safe_asset}, " if rotation.safe_asset else ""
    report.frame(
        targets_frame(targets),
        title=f"A rebalance at the {targets.date.date()} close would pick",
        caption=f"{in_safe}{targets.cash_pct:.1f}% in cash",
    )
    rows = contributions_frame(first.contributions)
    shown = rows if args.top <= 0 else rows.head(args.top)
    report.frame(
        shown,
        title=f"{len(shown)} of {len(rows)} tickers by P&L ({first.result.engine})",
        caption="contribution in % of the initial equity" + ("" if len(shown) == len(rows) else "; --top 0 shows all"),
    )
    output.export(
        report,
        pd.concat(
            [portfolio_trades_frame(run.result.trades, run.result.engine) for run in result.runs], ignore_index=True
        ),
        args.export,
    )
    return 0


COMMAND = Command(
    name="rotation-backtest",
    help="hold the strongest tickers of a watchlist, rebalanced weekly or monthly",
    add_arguments=add_arguments,
    run=run,
)
