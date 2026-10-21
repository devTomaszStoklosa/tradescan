"""Argument groups several commands share, and their choices."""

from __future__ import annotations

import argparse
from dataclasses import fields

from tradescan.backtest.metrics import Metrics
from tradescan.backtest.priority import priority_rules
from tradescan.backtest.rotation import DEFAULT_RANKING, Rebalance, ranking_rules
from tradescan.backtest.trade_rules import default_catalog
from tradescan.backtest.weighting import DEFAULT_WEIGHTING, weight_rules
from tradescan.services.composition import default_engines
from tradescan.services.rotation_sweep import ROTATION_SWEEP_SECTIONS
from tradescan.services.sweep import SWEEP_SECTIONS
from tradescan.signals import Family

ENGINE_CHOICES = [*default_engines(), "both"]


METRIC_CHOICES = [item.name for item in fields(Metrics)]


AXIS_HELP = (
    "parameter and values: target[.owner].name=FROM:TO:STEP or =V1,V2,... with target signal, entry, exit "
    "(owner: the exit rule), filter (owner: the entry filter) or settings "
    f"(owner: {', '.join(SWEEP_SECTIONS[:-1])} or {SWEEP_SECTIONS[-1]}), "
    "e.g. signal.oversold=5:20:5, exit.target.target_r=1,1.5,2 or filter.trend.period=100:200:50; "
    "give it twice for a grid"
)


ROTATION_AXIS_HELP = (
    "parameter and values: target[.owner].name=FROM:TO:STEP or =V1,V2,... with target ranking, weighting or "
    f"settings (owner: {' or '.join(ROTATION_SWEEP_SECTIONS)}), "
    "e.g. ranking.lookback=126:252:42, weighting.lookback=20,63 or settings.rotation.holdings=1:5:1; "
    "give it twice for a grid"
)


def add_universe_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-w", "--watchlist", help="watchlist name from the watchlists dir, or a file path")
    group.add_argument("-t", "--tickers", help="comma separated tickers, e.g. AAPL,MSFT,PKO.WA")


def add_data_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--period", help="yfinance period, e.g. 1y, 5y, max")
    parser.add_argument("--interval", help="yfinance interval (default 1d)")
    parser.add_argument("--no-cache", action="store_true", help="always download fresh data")


def add_signal_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--signals", help="comma separated signal names (default: all)")
    parser.add_argument("--family", help=f"comma separated families: {', '.join(f.value for f in Family)}")
    parser.add_argument("--direction", choices=["long", "short", "both"], default="both")


def add_account_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--equity", type=float, help="account size")
    parser.add_argument("--risk-pct", type=float, help="percent of equity risked per trade")
    parser.add_argument("--lot-size", type=float, help="size step, e.g. 0.0001 for crypto")


def add_backtest_setup_args(
    parser: argparse.ArgumentParser,
    *,
    benchmark_help: str = "benchmark the market filter compares (default: scan.benchmark from the settings)",
) -> None:
    """Everything a backtest setup takes apart from the ticker. `benchmark_help` is for the commands that pick
    the benchmark differently."""
    parser.add_argument("signal", help="signal name, see list-signals")
    add_data_args(parser)
    add_account_args(parser)
    parser.add_argument(
        "--entry",
        choices=default_catalog.entries.names(),
        help=f"entry order (default {default_catalog.default_entry})",
    )
    parser.add_argument(
        "--exits",
        help=f"exit rules on top of the stop, comma separated ({', '.join(default_catalog.exits.names())}); "
        f"'none' keeps only the stop (default {','.join(default_catalog.default_exits)})",
    )
    parser.add_argument(
        "--filters",
        help=f"entry filters a signal has to pass, comma separated ({', '.join(default_catalog.filters.names())}); "
        "default none",
    )
    parser.add_argument("--benchmark", help=benchmark_help)
    parser.add_argument("--atr-mult", type=float, help="stop distance in ATRs")
    parser.add_argument("--target-r", type=float, help="target as a multiple of the risk (target exit)")
    parser.add_argument("--max-hold", type=int, help="time exit after N bars (time exit)")
    parser.add_argument(
        "--max-units",
        type=int,
        help="pyramiding: the first entry plus the adds (1 turns it off; not for portfolio-backtest)",
    )
    parser.add_argument(
        "--add-every-atr", type=float, help="pyramiding: another unit every N ATRs in the trade's favour"
    )
    parser.add_argument("--commission-pct", type=float)
    parser.add_argument("--slippage-pct", type=float)
    parser.add_argument("--oos", type=float, help="out-of-sample share of the history in %% (10-50, default 30)")


def add_rotation_setup_args(parser: argparse.ArgumentParser) -> None:
    """Everything a rotation setup takes apart from the universe and the history."""
    parser.add_argument(
        "--rank",
        choices=[rule.name for rule in ranking_rules(priority_rules)],
        help=f"how the tickers are ranked (default {DEFAULT_RANKING})",
    )
    parser.add_argument("--holdings", type=int, help="tickers picked at each rebalance (default 5)")
    parser.add_argument("--rebalance", choices=[item.value for item in Rebalance], default=Rebalance.MONTHLY.value)
    parser.add_argument(
        "--weighting",
        choices=weight_rules.names(),
        help=f"how the picks share the equity (default {DEFAULT_WEIGHTING})",
    )
    parser.add_argument(
        "--absolute-lookback",
        type=int,
        help="a pick at or below 0 over this many bars goes to the safe asset (0: off, default 252)",
    )
    parser.add_argument(
        "--safe-asset", help="ticker for the slots of picks that fail the check, e.g. TLT (default: cash)"
    )
    parser.add_argument("--benchmark", help="buy & hold benchmark (default: the watchlist's, else scan.benchmark)")
    parser.add_argument("--equity", type=float, help="account size")
    parser.add_argument("--lot-size", type=float, help="size step, e.g. 0.0001 for crypto")
    parser.add_argument("--commission-pct", type=float)
    parser.add_argument("--slippage-pct", type=float)
    parser.add_argument("--oos", type=float, help="out-of-sample share of the run in %% (10-50, default 30)")
