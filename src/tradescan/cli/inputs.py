"""Turning parsed arguments into the use cases' inputs: universes, filters, overrides, rules, axes."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from tradescan.backtest.rotation import Rebalance
from tradescan.backtest.rotation_sweep import RotationSweepAxis, RotationSweepTarget
from tradescan.backtest.sweep import MAX_VALUES, SweepAxis, SweepTarget
from tradescan.backtest.trade_rules import RuleChoice, default_catalog
from tradescan.services.backtest import BacktestRequest
from tradescan.services.market_data import SignalFilter
from tradescan.services.rotation import RotationRequest
from tradescan.signals import Direction, Family
from tradescan.watchlist import Watchlist, from_tickers, load_watchlist

# Exit parameters with their own flags: flag attribute -> (exit rule, parameter).
EXIT_FLAGS = {"target_r": ("target", "target_r"), "max_hold": ("time", "max_hold_bars")}


def universe(args: argparse.Namespace) -> Watchlist:
    if args.tickers:
        return from_tickers(args.tickers)
    return load_watchlist(args.watchlist, Path(args.watchlists_dir))


def signal_filter(args: argparse.Namespace) -> SignalFilter:
    return SignalFilter(
        names=tuple(split(args.signals)),
        families=tuple(Family(name) for name in split(args.family)),
        direction=None if args.direction == "both" else Direction(args.direction),
    )


def account(args: argparse.Namespace) -> dict[str, float | None]:
    return {"equity": args.equity, "risk_pct": args.risk_pct, "lot_size": args.lot_size}


def overrides(sections: dict[str, dict[str, float | None]]) -> dict[str, dict[str, float]]:
    """Settings overrides from command-line flags; flags that were not given are left out."""
    result = {}
    for section, values in sections.items():
        given = {key: value for key, value in values.items() if value is not None}
        if given:
            result[section] = given
    return result


def exits(args: argparse.Namespace) -> tuple[RuleChoice, ...]:
    """The exit rules from `--exits` (default exits when not given, `none` for the stop only) and their flags."""
    if args.exits is None:
        names = list(default_catalog.default_exits)
    else:
        names = [name for name in split(args.exits) if name != "none"]
    params: dict[str, dict[str, float]] = {}
    for attribute, (rule, name) in EXIT_FLAGS.items():
        value = getattr(args, attribute)
        if value is None:
            continue
        if rule not in names:
            raise ValueError(f"--{attribute.replace('_', '-')} sets the {rule} exit, which --exits leaves out")
        params.setdefault(rule, {})[name] = value
    return tuple(RuleChoice(name, params.get(name, {})) for name in names)


def backtest_request(args: argparse.Namespace, ticker: str, engines: tuple[str, ...]) -> BacktestRequest:
    """The setup flags shared by `backtest`, `sweep`, `watchlist-backtest` and `portfolio-backtest`."""
    return BacktestRequest(
        ticker=ticker,
        signal=args.signal,
        engines=engines,
        settings=overrides(
            {
                "account": account(args),
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
        exits=exits(args),
        filters=tuple(RuleChoice(name) for name in split(args.filters)),
        benchmark=args.benchmark,
        period=args.period,
        interval=args.interval,
    )


def axis(text: str) -> SweepAxis:
    """`target[.owner].name=FROM:TO:STEP` or `target[.owner].name=V1,V2,...`, e.g. `signal.oversold=5:20:5`."""
    targets = [target.value for target in SweepTarget]
    target, owner, name, numbers = _axis_parts(text, targets, "signal.oversold=5:20:5")
    return SweepAxis(SweepTarget(target), name, numbers, owner=owner)


def rotation_axis(text: str) -> RotationSweepAxis:
    """A rotation sweep's axis in the same form, e.g. `ranking.lookback=126:252:42`."""
    targets = [target.value for target in RotationSweepTarget]
    target, owner, name, numbers = _axis_parts(text, targets, "ranking.lookback=126:252:42")
    return RotationSweepAxis(RotationSweepTarget(target), name, numbers, owner=owner)


def _axis_parts(text: str, targets: list[str], example: str) -> tuple[str, str, str, tuple[float, ...]]:
    """The target, the owner (empty without one), the name and the values of `--axis text`."""
    usage = f"--axis {text}: use target[.owner].name=FROM:TO:STEP or =V1,V2,..., e.g. {example}"
    key, separator, values = text.partition("=")
    parts = key.strip().split(".")
    if not separator or len(parts) not in (2, 3) or not all(parts):
        raise ValueError(usage)
    if parts[0] not in targets:
        raise ValueError(f"--axis {text}: the target must be one of {', '.join(targets)}")
    try:
        numbers = axis_values(values)
    except ValueError as error:
        raise ValueError(f"{usage} ({error})") from None
    return parts[0], parts[1] if len(parts) == 3 else "", parts[-1], numbers


def axis_values(text: str) -> tuple[float, ...]:
    if ":" not in text:
        return tuple(float(item) for item in split(text))
    start, stop, step = (float(part) for part in text.split(":"))
    if step <= 0 or stop < start:
        raise ValueError("FROM:TO:STEP needs TO >= FROM and a positive STEP")
    count = math.floor((stop - start) / step + 1e-9) + 1
    if count > MAX_VALUES:
        raise ValueError(f"that is {count} values, at most {MAX_VALUES}")
    return tuple(round(start + index * step, 10) for index in range(count))


def rotation_request(args: argparse.Namespace, universe: Watchlist, engines: tuple[str, ...]) -> RotationRequest:
    """The setup flags shared by `rotation-backtest` and `rotation-sweep`."""
    return RotationRequest(
        universe=universe,
        ranking=RuleChoice(args.rank) if args.rank else None,
        weighting=RuleChoice(args.weighting) if args.weighting else None,
        rebalance=Rebalance(args.rebalance),
        safe_asset=args.safe_asset,
        settings=overrides(
            {
                "account": {"equity": args.equity, "lot_size": args.lot_size},
                "backtest": {
                    "commission_pct": args.commission_pct,
                    "slippage_pct": args.slippage_pct,
                    "oos_pct": args.oos,
                },
                "rotation": {"holdings": args.holdings, "absolute_lookback": args.absolute_lookback},
            }
        ),
        benchmark=args.benchmark,
        period=args.period,
        interval=args.interval,
        engines=engines,
    )


def split(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]
