"""`tradescan watchlist-backtest`: one setup on every ticker."""

from __future__ import annotations

import argparse

from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import FEW_TRADES, pooled_frame, spread_frame, watchlist_export_frame, watchlist_rows_frame
from tradescan.services.watchlist_backtest import WatchlistBacktestRequest


def add_arguments(parser: argparse.ArgumentParser) -> None:
    arguments.add_backtest_setup_args(
        parser,
        benchmark_help="benchmark the market filter compares "
        "(default: the watchlist's '# benchmark:' line, else scan.benchmark from the settings)",
    )
    arguments.add_universe_args(parser)
    parser.add_argument(
        "--metric",
        choices=arguments.METRIC_CHOICES,
        default="expectancy_r",
        help="metric the tickers are ranked and spread by",
    )
    parser.add_argument("--top", type=int, default=25, help="tickers to show, best first (0: all)")
    parser.add_argument("--export", help="save every ticker with every period's metrics to .csv or .json")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = inputs.universe(args)
    output.loading(report, len(universe.tickers), args.period or settings.backtest.period)
    result = wiring.use_cases(settings, args).watchlist_backtest.run(
        WatchlistBacktestRequest(universe=universe, setup=inputs.backtest_request(args, "", ()))
    )
    output.missing(report, result.missing)
    base, metric = result.base, args.metric
    signal, config, rules = base.signal, base.config, base.rules
    exits = "; ".join(rule.describe() for rule in rules.exits) or "none"
    filters = "; ".join(rule.describe() for rule in rules.filters) or "none"
    benchmark = f" (benchmark {base.benchmark})" if base.benchmark else ""
    report.note(
        f"{signal.name} ({signal.direction.value}) on {len(result.rows)} tickers of {universe.name}, "
        f"vectorized engine. Filters: {filters}{benchmark}. Entry: {rules.entry.describe()}. "
        f"Stop {config.atr_mult:g} ATR{output.pyramiding(config)}, exits: {exits}. "
        f"Risk {config.risk_pct:g}%/trade, costs {config.commission_pct:g}% + {config.slippage_pct:g}% slippage"
    )
    rows = watchlist_rows_frame(result, metric)
    shown = rows if args.top <= 0 else rows.head(args.top)
    report.frame(
        shown,
        title=f"{len(shown)} of {len(rows)} tickers, best {metric} first",
        caption=f"each ticker split at its own last {config.oos_pct:g}%; '-' = too little history to split"
        + ("" if len(shown) == len(rows) else "; --top 0 shows all, --export saves all"),
    )
    report.frame(
        spread_frame(result, metric),
        title=f"Spread of {metric} across tickers",
        caption=f"tickers without a value (e.g. no trades) are left out; fewer than {FEW_TRADES} trades is noise",
        show_index=True,
    )
    report.frame(pooled_frame(result), title="All tickers' trades pooled, in R", show_index=True)
    output.export(report, watchlist_export_frame(result), args.export)
    return 0


COMMAND = Command(
    name="watchlist-backtest",
    help="backtest one setup on every ticker of a watchlist, in-sample and out-of-sample",
    add_arguments=add_arguments,
    run=run,
)
