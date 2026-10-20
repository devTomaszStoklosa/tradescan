"""`tradescan backtest`: one signal on one ticker with one or both engines."""

from __future__ import annotations

import argparse

import pandas as pd

from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import metrics_to_frame, periods_to_frame, trades_to_frame
from tradescan.services.composition import default_engines


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ticker")
    arguments.add_backtest_setup_args(parser)
    parser.add_argument("--engine", choices=arguments.ENGINE_CHOICES, default="vectorized")
    parser.add_argument("--trades", type=int, default=10, help="recent trades to show")
    parser.add_argument("--export", help="save trades to .csv or .json")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    output.loading(report, 1, args.period or settings.backtest.period)
    engines = tuple(default_engines()) if args.engine == "both" else (args.engine,)
    result = wiring.use_cases(settings, args).backtest.run(inputs.backtest_request(args, args.ticker, engines))
    config, signal, rules = result.config, result.signal, result.rules
    exits = "; ".join(rule.describe() for rule in rules.exits) or "none"
    filters = "; ".join(rule.describe() for rule in rules.filters) or "none"
    benchmark = f" (benchmark {result.benchmark})" if result.benchmark else ""
    report.frame(
        metrics_to_frame(result.runs),
        title=f"{result.ticker} {signal.name} ({signal.direction.value}), "
        f"{result.close.index[0].date()} to {result.close.index[-1].date()}",
        caption=f"filters: {filters}{benchmark}. Entry: {rules.entry.describe()}. Stop {config.atr_mult:g} ATR"
        f"{output.pyramiding(config)}, exits: {exits}. "
        f"Risk {config.risk_pct:g}%/trade, costs {config.commission_pct:g}% + {config.slippage_pct:g}% slippage",
        show_index=True,
    )
    split = result.split
    if split is None:
        report.warning(f"History too short for an out-of-sample split at {config.oos_pct:g}%")
    else:
        report.frame(
            periods_to_frame(result.runs),
            title=f"In-sample {split.in_sample[0].date()} to {split.in_sample[1].date()}, "
            f"out-of-sample (last {split.oos_pct:g}%) "
            f"{split.out_of_sample[0].date()} to {split.out_of_sample[1].date()}",
            caption="Each period starts with fresh equity; out-of-sample signals only fire from the split on",
            show_index=True,
        )
    first = result.runs[0].result
    trades = trades_to_frame(first.trades)
    report.frame(trades.tail(args.trades), title=f"Last {args.trades} trades ({first.engine})")
    output.export(
        report,
        pd.concat([trades_to_frame(run.result.trades, run.result.engine) for run in result.runs], ignore_index=True),
        args.export,
    )
    return 0


COMMAND = Command(name="backtest", help="backtest one signal on one ticker", add_arguments=add_arguments, run=run)
