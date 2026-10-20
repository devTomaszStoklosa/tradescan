"""`tradescan portfolio-backtest`: one setup on a watchlist with one equity."""

from __future__ import annotations

import argparse
from dataclasses import replace

import pandas as pd

from tradescan.backtest.priority import DEFAULT_PRIORITY, priority_rules
from tradescan.backtest.trade_rules import RuleChoice
from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import contributions_frame, portfolio_metrics_frame, portfolio_trades_frame
from tradescan.services.composition import default_portfolio_engines
from tradescan.services.portfolio import PortfolioRequest


def add_arguments(parser: argparse.ArgumentParser) -> None:
    arguments.add_backtest_setup_args(
        parser,
        benchmark_help="benchmark for buy & hold and for the market filter "
        "(default: the watchlist's '# benchmark:' line, else scan.benchmark from the settings)",
    )
    arguments.add_universe_args(parser)
    parser.add_argument("--max-positions", type=int, help="open positions plus waiting entry orders (default 10)")
    parser.add_argument("--max-exposure", type=float, help="gross exposure cap in %% of equity (default 100)")
    parser.add_argument(
        "--priority",
        choices=priority_rules.names(),
        help=f"which signals go first when more fire than fit (default {DEFAULT_PRIORITY})",
    )
    parser.add_argument("--engine", choices=arguments.ENGINE_CHOICES, default="vectorized")
    parser.add_argument("--top", type=int, default=15, help="tickers to show, largest P&L first (0: all)")
    parser.add_argument("--export", help="save every engine's trades to .csv or .json")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = inputs.universe(args)
    output.loading(report, len(universe.tickers), args.period or settings.backtest.period)
    engines = tuple(default_portfolio_engines()) if args.engine == "both" else (args.engine,)
    setup = inputs.backtest_request(args, "", engines)
    limits = inputs.overrides(
        {"portfolio": {"max_positions": args.max_positions, "max_exposure_pct": args.max_exposure}}
    )
    request = PortfolioRequest(
        universe=universe,
        setup=replace(setup, settings={**setup.settings, **limits}),
        priority=RuleChoice(args.priority) if args.priority else None,
    )
    result = wiring.use_cases(settings, args).portfolio.run(request)
    output.missing(report, result.missing)
    base, portfolio = result.base, result.portfolio
    signal, config, rules = base.signal, base.config, base.rules
    exits = "; ".join(rule.describe() for rule in rules.exits) or "none"
    filters = "; ".join(rule.describe() for rule in rules.filters) or "none"
    tickers = len(result.runs[0].contributions)
    report.note(
        f"{signal.name} ({signal.direction.value}) on {tickers} tickers of {universe.name} with one equity: at most "
        f"{portfolio.max_positions} positions and {portfolio.max_exposure_pct:g}% exposure, "
        f"priority: {result.priority.describe()}. "
        f"Filters: {filters}. Entry: {rules.entry.describe()}. Stop {config.atr_mult:g} ATR, exits: {exits}. "
        f"Risk {config.risk_pct:g}%/trade, costs {config.commission_pct:g}% + {config.slippage_pct:g}% slippage"
    )
    split = result.split
    calendar = result.calendar
    report.frame(
        portfolio_metrics_frame(result),
        title=f"{universe.name} portfolio, {calendar[0].date()} to {calendar[-1].date()}",
        caption=f"buy & hold is {result.benchmark}'s, exposure the share of days with a position"
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
    first = result.runs[0]
    rows = contributions_frame(first.contributions)
    shown = rows if args.top <= 0 else rows.head(args.top)
    report.frame(
        shown,
        title=f"{len(shown)} of {len(rows)} tickers by P&L ({first.result.engine}), full history",
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
    name="portfolio-backtest",
    help="backtest one setup on every ticker of a watchlist with one shared equity",
    add_arguments=add_arguments,
    run=run,
)
