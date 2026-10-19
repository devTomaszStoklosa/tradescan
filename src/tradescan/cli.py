"""Command line interface: parses arguments, calls the use cases in `services`, renders the reports."""

from __future__ import annotations

import argparse
import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import fields, replace
from pathlib import Path

import pandas as pd
from rich.console import Console

from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.metrics import Metrics
from tradescan.backtest.priority import DEFAULT_PRIORITY, priority_rules
from tradescan.backtest.rotation import DEFAULT_RANKING, Rebalance, ranking_rules
from tradescan.backtest.sweep import MAX_VALUES, SweepAxis, SweepTarget
from tradescan.backtest.trade_rules import RuleChoice, default_catalog
from tradescan.backtest.walk_forward import DEFAULT_SELECTION_METRIC, SELECTION_METRICS, WindowScheme
from tradescan.backtest.weighting import DEFAULT_WEIGHTING, weight_rules
from tradescan.config import Settings, load_settings
from tradescan.data.provider import DataProvider
from tradescan.parallel import ProcessRunner
from tradescan.report.console import ConsoleReport
from tradescan.report.export import export_frame
from tradescan.report.tables import (
    FEW_TRADES,
    SCAN_COLUMNS,
    contributions_frame,
    edge_to_frame,
    hits_to_frame,
    metrics_to_frame,
    periods_to_frame,
    pooled_frame,
    portfolio_metrics_frame,
    portfolio_trades_frame,
    rotation_metrics_frame,
    signals_to_frame,
    spread_frame,
    sweep_cells_frame,
    sweep_to_frame,
    targets_frame,
    trades_to_frame,
    walk_forward_export_frame,
    walk_forward_metrics_frame,
    walk_forward_pick,
    walk_forward_windows_frame,
    watchlist_export_frame,
    watchlist_rows_frame,
)
from tradescan.services import (
    SWEEP_SECTIONS,
    BacktestRequest,
    EdgeRequest,
    MarketRequest,
    PortfolioRequest,
    RotationRequest,
    ScanRequest,
    SignalFilter,
    SweepRequest,
    UseCases,
    WalkForwardRequest,
    WatchlistBacktestRequest,
    build_scorer,
    build_use_cases,
    default_engines,
    default_portfolio_engines,
    default_provider,
)
from tradescan.signals import Direction, Family, default_registry
from tradescan.storage.database import Database
from tradescan.universes import SOURCES, update_universe
from tradescan.watchlist import Watchlist, from_tickers, load_watchlist

Handler = Callable[[argparse.Namespace, Settings, ConsoleReport], int]

ENGINE_CHOICES = [*default_engines(), "both"]
# Exit parameters with their own flags: flag attribute -> (exit rule, parameter).
EXIT_FLAGS = {"target_r": ("target", "target_r"), "max_hold": ("time", "max_hold_bars")}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
METRIC_CHOICES = [item.name for item in fields(Metrics)]
AXIS_HELP = (
    "parameter and values: target[.owner].name=FROM:TO:STEP or =V1,V2,... with target signal, entry, exit "
    "(owner: the exit rule), filter (owner: the entry filter) or settings "
    f"(owner: {', '.join(SWEEP_SECTIONS[:-1])} or {SWEEP_SECTIONS[-1]}), "
    "e.g. signal.oversold=5:20:5, exit.target.target_r=1,1.5,2 or filter.trend.period=100:200:50; "
    "give it twice for a grid"
)


# ---------------------------------------------------------------------------
# Wiring helpers


def _provider(settings: Settings, args: argparse.Namespace) -> DataProvider:
    return default_provider(settings, use_cache=not getattr(args, "no_cache", False))


def _use_cases(settings: Settings, args: argparse.Namespace) -> UseCases:
    return build_use_cases(settings, _provider(settings, args), runner=ProcessRunner())


def _universe(args: argparse.Namespace) -> Watchlist:
    if args.tickers:
        return from_tickers(args.tickers)
    return load_watchlist(args.watchlist, Path(args.watchlists_dir))


def _signal_filter(args: argparse.Namespace) -> SignalFilter:
    return SignalFilter(
        names=tuple(_split(args.signals)),
        families=tuple(Family(name) for name in _split(args.family)),
        direction=None if args.direction == "both" else Direction(args.direction),
    )


def _account(args: argparse.Namespace) -> dict[str, float | None]:
    return {"equity": args.equity, "risk_pct": args.risk_pct, "lot_size": args.lot_size}


def _overrides(sections: dict[str, dict[str, float | None]]) -> dict[str, dict[str, float]]:
    """Settings overrides from command-line flags; flags that were not given are left out."""
    result = {}
    for section, values in sections.items():
        given = {key: value for key, value in values.items() if value is not None}
        if given:
            result[section] = given
    return result


def _exits(args: argparse.Namespace) -> tuple[RuleChoice, ...]:
    """The exit rules from `--exits` (default exits when not given, `none` for the stop only) and their flags."""
    if args.exits is None:
        names = list(default_catalog.default_exits)
    else:
        names = [name for name in _split(args.exits) if name != "none"]
    params: dict[str, dict[str, float]] = {}
    for attribute, (rule, name) in EXIT_FLAGS.items():
        value = getattr(args, attribute)
        if value is None:
            continue
        if rule not in names:
            raise ValueError(f"--{attribute.replace('_', '-')} sets the {rule} exit, which --exits leaves out")
        params.setdefault(rule, {})[name] = value
    return tuple(RuleChoice(name, params.get(name, {})) for name in names)


def _pyramiding(config: BacktestConfig) -> str:
    """The pyramiding of a backtest for its caption; empty without it."""
    if config.max_units <= 1:
        return ""
    return f", pyramiding up to {config.max_units} units {config.add_every_atr:g} ATR apart"


def _backtest_request(args: argparse.Namespace, ticker: str, engines: tuple[str, ...]) -> BacktestRequest:
    """The setup flags shared by `backtest`, `sweep`, `watchlist-backtest` and `portfolio-backtest`."""
    return BacktestRequest(
        ticker=ticker,
        signal=args.signal,
        engines=engines,
        settings=_overrides(
            {
                "account": _account(args),
                "risk": {"atr_mult": args.atr_mult},
                "backtest": {
                    "commission_pct": args.commission_pct,
                    "slippage_pct": args.slippage_pct,
                    "oos_pct": args.oos,
                },
                "pyramid": {"max_units": args.max_units, "add_every_atr": args.add_every_atr},
            }
        ),
        entry=RuleChoice(args.entry) if args.entry else None,
        exits=_exits(args),
        filters=tuple(RuleChoice(name) for name in _split(args.filters)),
        benchmark=args.benchmark,
        period=args.period,
        interval=args.interval,
    )


def _axis(text: str) -> SweepAxis:
    """`target[.owner].name=FROM:TO:STEP` or `target[.owner].name=V1,V2,...`, e.g. `signal.oversold=5:20:5`."""
    usage = f"--axis {text}: use target[.owner].name=FROM:TO:STEP or =V1,V2,..., e.g. signal.oversold=5:20:5"
    key, separator, values = text.partition("=")
    parts = key.strip().split(".")
    if not separator or len(parts) not in (2, 3) or not all(parts):
        raise ValueError(usage)
    if parts[0] not in {target.value for target in SweepTarget}:
        raise ValueError(
            f"--axis {text}: the target must be one of {', '.join(target.value for target in SweepTarget)}"
        )
    try:
        numbers = _axis_values(values)
    except ValueError as error:
        raise ValueError(f"{usage} ({error})") from None
    return SweepAxis(SweepTarget(parts[0]), parts[-1], numbers, owner=parts[1] if len(parts) == 3 else "")


def _axis_values(text: str) -> tuple[float, ...]:
    if ":" not in text:
        return tuple(float(item) for item in _split(text))
    start, stop, step = (float(part) for part in text.split(":"))
    if step <= 0 or stop < start:
        raise ValueError("FROM:TO:STEP needs TO >= FROM and a positive STEP")
    count = math.floor((stop - start) / step + 1e-9) + 1
    if count > MAX_VALUES:
        raise ValueError(f"that is {count} values, at most {MAX_VALUES}")
    return tuple(round(start + index * step, 10) for index in range(count))


def _split(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _missing(report: ConsoleReport, missing: Sequence[str]) -> None:
    if missing:
        report.warning(f"No data for: {', '.join(missing)}")


def _export(report: ConsoleReport, frame: pd.DataFrame, target: str | None) -> None:
    if target:
        report.note(f"Saved {export_frame(frame, Path(target))}")


def _loading(report: ConsoleReport, count: int, period: str) -> None:
    report.note(f"Loading {count} tickers ({period})...")


# ---------------------------------------------------------------------------
# Commands


def cmd_list_signals(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    signals = default_registry.select()
    report.frame(signals_to_frame(signals, build_scorer(settings)), title=f"{len(signals)} signals")
    return 0


def cmd_scan(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    _loading(report, len(universe.tickers) + 1, args.period or settings.data.period)
    result = _use_cases(settings, args).scan.run(
        ScanRequest(
            universe=universe,
            signals=_signal_filter(args),
            settings=_overrides(
                {"account": _account(args), "scan": {"fresh_bars": args.fresh, "min_score": args.min_score}}
            ),
            benchmark=args.benchmark,
            period=args.period,
            interval=args.interval,
        )
    )
    _missing(report, result.missing)
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
    _export(report, hits_to_frame(result.hits), args.export)
    return 0


def cmd_market(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    _loading(report, len(universe.tickers) + 1, args.period or settings.data.period)
    result = _use_cases(settings, args).market.run(
        MarketRequest(universe=universe, benchmark=args.benchmark, period=args.period, interval=args.interval)
    )
    _missing(report, result.missing)
    report.regime(result.regime)
    return 0


def cmd_edge(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    _loading(report, len(universe.tickers), args.period or settings.backtest.period)
    result = _use_cases(settings, args).edge.run(
        EdgeRequest(
            universe=universe,
            signals=_signal_filter(args),
            horizons=tuple(int(value) for value in _split(args.horizons)),
            min_events=args.min_events,
            period=args.period,
            interval=args.interval,
        )
    )
    _missing(report, result.missing)
    frame = edge_to_frame(result.rows)
    report.frame(
        frame,
        title=f"Signal edge on {universe.name} ({result.tickers} tickers)",
        caption="Returns in the signal's direction from the next open; 'vs base' = minus the average of all bars. "
        "Small N is noise; current watchlists carry survivorship bias.",
    )
    _export(report, frame, args.export)
    return 0


def cmd_backtest(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    _loading(report, 1, args.period or settings.backtest.period)
    engines = tuple(default_engines()) if args.engine == "both" else (args.engine,)
    result = _use_cases(settings, args).backtest.run(_backtest_request(args, args.ticker, engines))
    config, signal, rules = result.config, result.signal, result.rules
    exits = "; ".join(rule.describe() for rule in rules.exits) or "none"
    filters = "; ".join(rule.describe() for rule in rules.filters) or "none"
    benchmark = f" (benchmark {result.benchmark})" if result.benchmark else ""
    report.frame(
        metrics_to_frame(result.runs),
        title=f"{result.ticker} {signal.name} ({signal.direction.value}), "
        f"{result.close.index[0].date()} to {result.close.index[-1].date()}",
        caption=f"filters: {filters}{benchmark}. Entry: {rules.entry.describe()}. Stop {config.atr_mult:g} ATR"
        f"{_pyramiding(config)}, exits: {exits}. "
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
    _export(
        report,
        pd.concat([trades_to_frame(run.result.trades, run.result.engine) for run in result.runs], ignore_index=True),
        args.export,
    )
    return 0


def cmd_sweep(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    _loading(report, 1, args.period or settings.backtest.period)
    axes = tuple(_axis(text) for text in args.axis)
    result = _use_cases(settings, args).sweep.run(
        SweepRequest(setup=_backtest_request(args, args.ticker, ()), axes=axes)
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
    _export(report, sweep_cells_frame(result), args.export)
    return 0


def cmd_walk_forward(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    if args.oos is not None:
        raise ValueError(
            "--oos sets a backtest's out-of-sample share; a walk-forward's windows split the history "
            "(--windows, --in-sample-ratio)"
        )
    _loading(report, 1, args.period or settings.backtest.period)
    setup = _backtest_request(args, args.ticker, ())
    windows = _overrides(
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
        axes=tuple(_axis(text) for text in args.axis),
        scheme=WindowScheme(args.scheme),
        metric=args.metric,
    )
    result = _use_cases(settings, args).walk_forward.run(request)
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
    _export(report, walk_forward_export_frame(result), args.export)
    return 0


def cmd_watchlist_backtest(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    _loading(report, len(universe.tickers), args.period or settings.backtest.period)
    result = _use_cases(settings, args).watchlist_backtest.run(
        WatchlistBacktestRequest(universe=universe, setup=_backtest_request(args, "", ()))
    )
    _missing(report, result.missing)
    base, metric = result.base, args.metric
    signal, config, rules = base.signal, base.config, base.rules
    exits = "; ".join(rule.describe() for rule in rules.exits) or "none"
    filters = "; ".join(rule.describe() for rule in rules.filters) or "none"
    benchmark = f" (benchmark {base.benchmark})" if base.benchmark else ""
    report.note(
        f"{signal.name} ({signal.direction.value}) on {len(result.rows)} tickers of {universe.name}, "
        f"vectorized engine. Filters: {filters}{benchmark}. Entry: {rules.entry.describe()}. "
        f"Stop {config.atr_mult:g} ATR{_pyramiding(config)}, exits: {exits}. "
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
    _export(report, watchlist_export_frame(result), args.export)
    return 0


def cmd_portfolio_backtest(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    _loading(report, len(universe.tickers), args.period or settings.backtest.period)
    engines = tuple(default_portfolio_engines()) if args.engine == "both" else (args.engine,)
    setup = _backtest_request(args, "", engines)
    limits = _overrides({"portfolio": {"max_positions": args.max_positions, "max_exposure_pct": args.max_exposure}})
    request = PortfolioRequest(
        universe=universe,
        setup=replace(setup, settings={**setup.settings, **limits}),
        priority=RuleChoice(args.priority) if args.priority else None,
    )
    result = _use_cases(settings, args).portfolio.run(request)
    _missing(report, result.missing)
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
    _export(
        report,
        pd.concat(
            [portfolio_trades_frame(run.result.trades, run.result.engine) for run in result.runs], ignore_index=True
        ),
        args.export,
    )
    return 0


def cmd_rotation_backtest(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    universe = _universe(args)
    _loading(report, len(universe.tickers), args.period or settings.backtest.period)
    overrides = _overrides(
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
    result = _use_cases(settings, args).rotation.run(request)
    _missing(report, result.missing)
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
    _export(report, portfolio_trades_frame(run.trades, run.engine), args.export)
    return 0


def cmd_update_universes(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    wanted = set(_split(args.only))
    unknown = wanted - {source.name for source in SOURCES}
    if unknown:
        raise ValueError(
            f"Unknown universe(s): {', '.join(sorted(unknown))}. Use: {', '.join(s.name for s in SOURCES)}"
        )
    failures = 0
    for source in SOURCES:
        if wanted and source.name not in wanted:
            continue
        try:
            result = update_universe(source, Path(args.watchlists_dir))
        except (OSError, ValueError) as error:
            failures += 1
            report.warning(f"{source.title}: not updated, the existing file is kept ({error})")
            continue
        if result.created:
            changes = "created"
        elif result.added or result.removed:
            changes = f"+{len(result.added)} / -{len(result.removed)}"
        else:
            changes = "no changes"
        report.note(f"{source.title}: {len(result.tickers)} tickers -> {result.path} ({changes})")
        if result.added:
            report.note(f"  added: {', '.join(result.added)}")
        if result.removed:
            report.note(f"  removed: {', '.join(result.removed)}")
    return 1 if failures else 0


def cmd_serve(args: argparse.Namespace, settings: Settings, report: ConsoleReport) -> int:
    try:
        import uvicorn

        from tradescan.api.app import create_app
    except ImportError as error:
        raise ImportError(f"The web server needs the api extra: pip install -e .[api] ({error})") from error

    if args.host not in LOOPBACK_HOSTS:
        report.warning("The API has no authentication. Binding beyond localhost exposes it to your network.")
    static = Path(args.static)
    if not static.is_dir():
        report.warning(f"{static} not found: serving the API only. Build the UI with `npm run build` in frontend/.")
    database = Database(Path(args.db))
    database.migrate()  # a file that is not a tradescan database stops the server before it starts
    app = create_app(
        settings=settings,
        provider=_provider(settings, args),
        watchlists_dir=Path(args.watchlists_dir),
        static_dir=static if static.is_dir() else None,
        runner=ProcessRunner(),
        database=database,
    )
    report.note(f"tradescan UI on http://{args.host}:{args.port}, pinned runs and the journal in {database.location}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


# ---------------------------------------------------------------------------
# Argument parsing


def _add_universe_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-w", "--watchlist", help="watchlist name from the watchlists dir, or a file path")
    group.add_argument("-t", "--tickers", help="comma separated tickers, e.g. AAPL,MSFT,PKO.WA")


def _add_data_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--period", help="yfinance period, e.g. 1y, 5y, max")
    parser.add_argument("--interval", help="yfinance interval (default 1d)")
    parser.add_argument("--no-cache", action="store_true", help="always download fresh data")


def _add_signal_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--signals", help="comma separated signal names (default: all)")
    parser.add_argument("--family", help=f"comma separated families: {', '.join(f.value for f in Family)}")
    parser.add_argument("--direction", choices=["long", "short", "both"], default="both")


def _add_account_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--equity", type=float, help="account size")
    parser.add_argument("--risk-pct", type=float, help="percent of equity risked per trade")
    parser.add_argument("--lot-size", type=float, help="size step, e.g. 0.0001 for crypto")


def _add_backtest_setup_args(
    parser: argparse.ArgumentParser,
    *,
    benchmark_help: str = "benchmark the market filter compares (default: scan.benchmark from the settings)",
) -> None:
    """Everything a backtest setup takes apart from the ticker. `benchmark_help` is for the commands that pick
    the benchmark differently."""
    parser.add_argument("signal", help="signal name, see list-signals")
    _add_data_args(parser)
    _add_account_args(parser)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradescan",
        description="Trading signal scanner: vectorized pandas signals on yfinance data, optional backtrader check.",
    )
    parser.add_argument("--config", default="config/settings.toml", help="settings file (TOML)")
    parser.add_argument("--watchlists-dir", default="config/watchlists")
    parser.add_argument("-v", "--verbose", action="store_true", help="show data download warnings")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list-signals", help="show all signals with family, direction and weight")
    listing.set_defaults(handler=cmd_list_signals)

    scan = commands.add_parser("scan", help="find fresh signals, score them and plan the risk")
    _add_universe_args(scan)
    _add_data_args(scan)
    _add_signal_filter_args(scan)
    _add_account_args(scan)
    scan.add_argument("--fresh", type=int, help="signal must have fired within the last N bars")
    scan.add_argument("--min-score", type=float, help="hide setups scoring below this")
    scan.add_argument("--top", type=int, default=25, help="rows to show")
    scan.add_argument("--benchmark", help="benchmark ticker for regime (default from watchlist or settings)")
    scan.add_argument("--export", help="save all hits to .csv or .json")
    scan.set_defaults(handler=cmd_scan)

    market = commands.add_parser("market", help="market regime: benchmark trend and breadth")
    _add_universe_args(market)
    _add_data_args(market)
    market.add_argument("--benchmark")
    market.set_defaults(handler=cmd_market)

    edge = commands.add_parser("edge", help="historical forward returns after each signal")
    _add_universe_args(edge)
    _add_data_args(edge)
    _add_signal_filter_args(edge)
    edge.add_argument("--horizons", default="5,10,20", help="bars after the signal, comma separated")
    edge.add_argument("--min-events", type=int, default=0, help="hide signals with fewer events")
    edge.add_argument("--export", help="save to .csv or .json")
    edge.set_defaults(handler=cmd_edge)

    backtest = commands.add_parser("backtest", help="backtest one signal on one ticker")
    backtest.add_argument("ticker")
    _add_backtest_setup_args(backtest)
    backtest.add_argument("--engine", choices=ENGINE_CHOICES, default="vectorized")
    backtest.add_argument("--trades", type=int, default=10, help="recent trades to show")
    backtest.add_argument("--export", help="save trades to .csv or .json")
    backtest.set_defaults(handler=cmd_backtest)

    sweep = commands.add_parser(
        "sweep", help="backtest one or two parameters over a range, in-sample and out-of-sample"
    )
    sweep.add_argument("ticker")
    _add_backtest_setup_args(sweep)
    sweep.add_argument("--axis", action="append", required=True, help=AXIS_HELP)
    sweep.add_argument("--metric", choices=METRIC_CHOICES, default="sharpe", help="metric shown in the grids")
    sweep.add_argument("--export", help="save every combination with both periods' metrics to .csv or .json")
    sweep.set_defaults(handler=cmd_sweep)

    walk_forward = commands.add_parser(
        "walk-forward",
        help="re-tune one or two parameters on rolling in-sample windows and trade each pick on the next window",
    )
    walk_forward.add_argument("ticker")
    _add_backtest_setup_args(walk_forward)
    walk_forward.add_argument("--axis", action="append", required=True, help=AXIS_HELP)
    walk_forward.add_argument("--windows", type=int, help="out-of-sample windows (2-20, default 5)")
    walk_forward.add_argument(
        "--in-sample-ratio",
        type=float,
        help="each in-sample window is this many times as long as an out-of-sample one (default 3)",
    )
    walk_forward.add_argument(
        "--scheme",
        choices=[scheme.value for scheme in WindowScheme],
        default=WindowScheme.ROLLING.value,
        help="rolling: in-sample windows of fixed length; anchored: in-sample windows from the first bar",
    )
    walk_forward.add_argument(
        "--min-trades", type=int, help="closed in-sample trades a setting needs to be picked (default 10)"
    )
    walk_forward.add_argument(
        "--metric",
        choices=SELECTION_METRICS,
        default=DEFAULT_SELECTION_METRIC,
        help="metric each in-sample window picks by",
    )
    walk_forward.add_argument("--trades", type=int, default=10, help="recent out-of-sample trades to show")
    walk_forward.add_argument(
        "--export", help="save every window with its pick and both periods' metrics to .csv or .json"
    )
    walk_forward.set_defaults(handler=cmd_walk_forward)

    watchlist_backtest = commands.add_parser(
        "watchlist-backtest", help="backtest one setup on every ticker of a watchlist, in-sample and out-of-sample"
    )
    _add_backtest_setup_args(
        watchlist_backtest,
        benchmark_help="benchmark the market filter compares "
        "(default: the watchlist's '# benchmark:' line, else scan.benchmark from the settings)",
    )
    _add_universe_args(watchlist_backtest)
    watchlist_backtest.add_argument(
        "--metric", choices=METRIC_CHOICES, default="expectancy_r", help="metric the tickers are ranked and spread by"
    )
    watchlist_backtest.add_argument("--top", type=int, default=25, help="tickers to show, best first (0: all)")
    watchlist_backtest.add_argument("--export", help="save every ticker with every period's metrics to .csv or .json")
    watchlist_backtest.set_defaults(handler=cmd_watchlist_backtest)

    portfolio = commands.add_parser(
        "portfolio-backtest", help="backtest one setup on every ticker of a watchlist with one shared equity"
    )
    _add_backtest_setup_args(
        portfolio,
        benchmark_help="benchmark for buy & hold and for the market filter "
        "(default: the watchlist's '# benchmark:' line, else scan.benchmark from the settings)",
    )
    _add_universe_args(portfolio)
    portfolio.add_argument("--max-positions", type=int, help="open positions plus waiting entry orders (default 10)")
    portfolio.add_argument("--max-exposure", type=float, help="gross exposure cap in %% of equity (default 100)")
    portfolio.add_argument(
        "--priority",
        choices=priority_rules.names(),
        help=f"which signals go first when more fire than fit (default {DEFAULT_PRIORITY})",
    )
    portfolio.add_argument("--engine", choices=ENGINE_CHOICES, default="vectorized")
    portfolio.add_argument("--top", type=int, default=15, help="tickers to show, largest P&L first (0: all)")
    portfolio.add_argument("--export", help="save every engine's trades to .csv or .json")
    portfolio.set_defaults(handler=cmd_portfolio_backtest)

    rotation = commands.add_parser(
        "rotation-backtest", help="hold the strongest tickers of a watchlist, rebalanced weekly or monthly"
    )
    _add_universe_args(rotation)
    _add_data_args(rotation)
    rotation.add_argument(
        "--rank",
        choices=[rule.name for rule in ranking_rules(priority_rules)],
        help=f"how the tickers are ranked (default {DEFAULT_RANKING})",
    )
    rotation.add_argument("--holdings", type=int, help="tickers picked at each rebalance (default 5)")
    rotation.add_argument("--rebalance", choices=[item.value for item in Rebalance], default=Rebalance.MONTHLY.value)
    rotation.add_argument(
        "--weighting",
        choices=weight_rules.names(),
        help=f"how the picks share the equity (default {DEFAULT_WEIGHTING})",
    )
    rotation.add_argument(
        "--absolute-lookback",
        type=int,
        help="a pick at or below 0 over this many bars goes to the safe asset (0: off, default 252)",
    )
    rotation.add_argument(
        "--safe-asset", help="ticker for the slots of picks that fail the check, e.g. TLT (default: cash)"
    )
    rotation.add_argument("--benchmark", help="buy & hold benchmark (default: the watchlist's, else scan.benchmark)")
    rotation.add_argument("--equity", type=float, help="account size")
    rotation.add_argument("--lot-size", type=float, help="size step, e.g. 0.0001 for crypto")
    rotation.add_argument("--commission-pct", type=float)
    rotation.add_argument("--slippage-pct", type=float)
    rotation.add_argument("--oos", type=float, help="out-of-sample share of the run in %% (10-50, default 30)")
    rotation.add_argument("--top", type=int, default=15, help="tickers to show, largest P&L first (0: all)")
    rotation.add_argument("--export", help="save the trades to .csv or .json")
    rotation.set_defaults(handler=cmd_rotation_backtest)

    universes = commands.add_parser(
        "update-universes", help="refresh the S&P 500 and Nasdaq-100 watchlists from Wikipedia"
    )
    universes.add_argument("--only", help=f"comma separated: {', '.join(source.name for source in SOURCES)}")
    universes.set_defaults(handler=cmd_update_universes)

    serve = commands.add_parser("serve", help="run the web UI and HTTP API (needs the api extra)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--static", default="frontend/dist", help="built frontend to serve")
    serve.add_argument("--db", default="tradescan.db", help="SQLite file for the pinned runs and the trade journal")
    serve.add_argument("--no-cache", action="store_true", help="always download fresh data")
    serve.set_defaults(handler=cmd_serve)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.verbose else logging.ERROR, format="%(levelname)s %(message)s")
    if not args.verbose:
        # Missing tickers are already reported once by the scanner; yfinance would log every failure again.
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    report = ConsoleReport(Console())
    try:
        settings = load_settings(Path(args.config))
        handler: Handler = args.handler
        return handler(args, settings, report)
    except (FileNotFoundError, KeyError, ValueError, ImportError) as error:
        message = error.args[0] if error.args else str(error)
        report.warning(f"Error: {message}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
