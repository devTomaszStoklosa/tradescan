"""`tradescan rotation-backtest`: hold a watchlist's strongest tickers."""

from __future__ import annotations

import argparse

from tradescan.backtest.priority import priority_rules
from tradescan.backtest.rotation import DEFAULT_RANKING, Rebalance, ranking_rules
from tradescan.backtest.trade_rules import RuleChoice
from tradescan.backtest.weighting import DEFAULT_WEIGHTING, weight_rules
from tradescan.cli import arguments, inputs, output, wiring
from tradescan.cli.command import Command
from tradescan.config import Settings
from tradescan.report.console import ConsoleReport
from tradescan.report.tables import contributions_frame, portfolio_trades_frame, rotation_metrics_frame, targets_frame
from tradescan.services.rotation import RotationRequest


def add_arguments(parser: argparse.ArgumentParser) -> None:
    arguments.add_universe_args(parser)
    arguments.add_data_args(parser)
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
    parser.add_argument("--top", type=int, default=15, help="tickers to show, largest P&L first (0: all)")
    parser.add_argument("--export", help="save the trades to .csv or .json")


def run(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = inputs.universe(args)
    output.loading(report, len(universe.tickers), args.period or settings.backtest.period)
    overrides = inputs.overrides(
        {
            "account": {"equity": args.equity, "lot_size": args.lot_size},
            "backtest": {"commission_pct": args.commission_pct, "slippage_pct": args.slippage_pct, "oos_pct": args.oos},
            "rotation": {"holdings": args.holdings, "absolute_lookback": args.absolute_lookback},
        }
    )
    request = RotationRequest(
        universe=universe,
        ranking=RuleChoice(args.rank) if args.rank else None,
        weighting=RuleChoice(args.weighting) if args.weighting else None,
        rebalance=Rebalance(args.rebalance),
        safe_asset=args.safe_asset,
        settings=overrides,
        benchmark=args.benchmark,
        period=args.period,
        interval=args.interval,
    )
    result = wiring.use_cases(settings, args).rotation.run(request)
    output.missing(report, result.missing)
    rotation, config, run = result.rotation, result.config, result.result
    defensive = rotation.safe_asset or "cash"
    check = (
        f"a pick at or below 0 over {rotation.absolute_lookback} bars goes to {defensive}"
        if rotation.checks_momentum
        else "no absolute momentum check"
    )
    tickers = sum(row.ticker in universe.tickers for row in result.contributions)
    report.note(
        f"Top {rotation.holdings} of {tickers} tickers of {universe.name}, rebalanced {rotation.rebalance.value}. "
        f"Ranking: {result.ranking.describe()}. Weights: {result.weighting.describe()}. Absolute momentum: {check}. "
        f"Costs {config.commission_pct:g}% + {config.slippage_pct:g}% slippage"
    )
    split = result.split
    dates = run.equity.index
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
    targets = run.targets
    in_safe = f"{targets.safe_pct:.1f}% in {rotation.safe_asset}, " if rotation.safe_asset else ""
    report.frame(
        targets_frame(targets),
        title=f"A rebalance at the {targets.date.date()} close would pick",
        caption=f"{in_safe}{targets.cash_pct:.1f}% in cash",
    )
    rows = contributions_frame(result.contributions)
    shown = rows if args.top <= 0 else rows.head(args.top)
    report.frame(
        shown,
        title=f"{len(shown)} of {len(rows)} tickers by P&L",
        caption="contribution in % of the initial equity" + ("" if len(shown) == len(rows) else "; --top 0 shows all"),
    )
    output.export(report, portfolio_trades_frame(run.trades, run.engine), args.export)
    return 0


COMMAND = Command(
    name="rotation-backtest",
    help="hold the strongest tickers of a watchlist, rebalanced weekly or monthly",
    add_arguments=add_arguments,
    run=run,
)
