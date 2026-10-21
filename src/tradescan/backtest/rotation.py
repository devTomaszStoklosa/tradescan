"""Momentum rotation: hold the strongest tickers of a watchlist with one shared equity, rebalanced on a calendar.

At the close of the last day of every week or month of the shared calendar (`Rebalance`), the ranking rule ranks
every ticker that has a score, a raw weight (`weighting`) and, with the check on, an absolute momentum, and the top
`holdings` are picked. Rankings are priority rules that score tickers from their bars (`ranking_rules`). A pick
whose return over `absolute_lookback` bars is at or below 0 hands its slot to the safe asset, or to cash without
one; a safe asset without a bar yet leaves it in cash. The picks share the equity by the weighting rule, and slots
without a pick stay in cash.

Target shares are a share of the equity at the close divided by the close, rounded down to lots. Only the
difference to the shares held trades, with a market order for the ticker's next open; an order whose ticker has no
bar before the next rebalance is dropped. Fills take the backtest's slippage and commission, and cash never limits
them, so a gap can take the holdings slightly above 100% of equity.

A ticker ranks by its last bar on a day without a bar of its own, while its bars go on. A ticker whose bars end
keeps what it holds, marked to its last close, until the end, and the rebalances share out the rest of the equity.

A trade is a holding: from the buy that opens a position to the sale that empties it, with every add, trim and
commission in its P&L. Without a stop it has no R multiple. A run starts at the close of the first rebalance at
which a ticker can be picked, so the warm-up of the lookbacks is not counted as time in cash.

Both rotation engines prepare the assets with `prepare`, pick with `targets` and size the orders with
`rebalance_orders`; only the order execution differs between them, as for the portfolio engines.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

import numpy as np
import pandas as pd

from tradescan.backtest.base import BacktestConfig, ExitReason, Trade
from tradescan.backtest.portfolio import PortfolioTrade, shared_calendar
from tradescan.backtest.priority import MomentumPriority, PriorityInputs, PriorityRule
from tradescan.backtest.rules import Bars, RuleRegistry
from tradescan.backtest.vectorized import FillModel
from tradescan.backtest.weighting import WeightRule, book_weights
from tradescan.signals.base import Direction

EPSILON = 1e-9  # share counts closer to 0 or to a whole lot than this count as there


class Rebalance(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    @property
    def period(self) -> str:
        """The pandas period whose last day rebalances."""
        return _PERIODS[self]


_PERIODS = {Rebalance.WEEKLY: "W", Rebalance.MONTHLY: "M"}


@dataclass(frozen=True)
class RotationConfig:
    holdings: int = 5  # tickers picked at each rebalance
    absolute_lookback: int = 252  # bars of the absolute momentum check; 0 turns it off
    rebalance: Rebalance = Rebalance.MONTHLY
    safe_asset: str | None = None  # takes the slots of picks that fail the check; None: cash

    @property
    def checks_momentum(self) -> bool:
        return self.absolute_lookback > 0


def ranking_rules(priorities: RuleRegistry[PriorityRule]) -> list[type[PriorityRule]]:
    """The priority rules a rotation can rank by: those that score the tickers from their bars alone."""
    return [rule for rule in priorities.classes() if not rule.needs_scan]


DEFAULT_RANKING = MomentumPriority.name


def rebalance_days(calendar: pd.DatetimeIndex, rebalance: Rebalance, start: pd.Timestamp | None = None) -> np.ndarray:
    """The position of the last day of every week or month of the calendar but the last one, which may go on; with
    `start`, only those from that date on."""
    periods = calendar.to_period(rebalance.period)
    days = np.flatnonzero(np.asarray(periods[1:] != periods[:-1]))
    return days if start is None else days[calendar[days] >= start]


@dataclass(frozen=True)
class Pick:
    ticker: str
    score: float  # the ranking's
    momentum: float  # return over the absolute momentum lookback; NaN with the check off
    weight_pct: float  # the pick's share of equity
    held: bool  # False when its absolute momentum hands its slot to the safe asset or cash


@dataclass(frozen=True)
class Targets:
    """What a rebalance at the close of `date` holds."""

    date: pd.Timestamp
    picks: tuple[Pick, ...]  # by rank
    safe_pct: float  # share of equity in the safe asset for the picks that failed the check
    cash_pct: float  # share of equity left in cash
    weights: Mapping[int, float] = field(default_factory=dict, repr=False)  # by asset position, a fraction of equity


@dataclass(frozen=True)
class RotationResult:
    engine: str
    tickers: tuple[str, ...]  # the watchlist in its order, then the safe asset when it is not in it
    equity: pd.Series  # at each close from the first rebalance with a pick
    holdings: pd.Series  # tickers held at each close, the safe asset included
    exposure_pct: pd.Series  # gross value of the holdings at each close, % of equity
    safe_pct: pd.Series  # value of the safe asset at each close, % of equity
    trades: tuple[PortfolioTrade, ...]  # holdings by entry date, then ticker order
    rebalances: int  # rebalance closes in the run
    orders: int  # orders filled
    unfilled: int  # orders dropped because their ticker had no bar before the next rebalance
    traded_value: float  # value of every fill
    commissions: float
    targets: Targets  # what a rebalance at the last close would hold


class RotationEngine(Protocol):
    name: str

    def run(
        self,
        frames: Mapping[str, pd.DataFrame],
        config: BacktestConfig,
        rotation: RotationConfig,
        ranking: PriorityRule,
        weighting: WeightRule,
        safe_frame: pd.DataFrame | None = None,
        start: pd.Timestamp | None = None,
    ) -> RotationResult:
        """`frames` holds the watchlist's bars in its order; `safe_frame` the safe asset's when it is not in it.
        With `start`, the run rebalances from that date on only."""
        ...


@dataclass(frozen=True, eq=False)
class _Asset:
    ticker: str
    bars: Bars
    days: np.ndarray  # the position of each bar in the shared calendar
    scores: np.ndarray  # the ranking's; NaN for a safe asset outside the watchlist
    weights: np.ndarray  # raw weights
    momentum: np.ndarray  # return over the absolute momentum lookback

    def last_bar(self, day: int) -> int:
        """The asset's last bar at or before calendar day `day`; -1 before its first bar."""
        return int(np.searchsorted(self.days, day, side="right")) - 1

    def trading(self, bar: int, day: int) -> bool:
        """Whether the asset still trades on calendar day `day`, whose last bar is `bar`."""
        return bar >= 0 and (self.days[bar] == day or bar + 1 < len(self.bars))


@dataclass(frozen=True, eq=False)
class RotationSetup:
    calendar: pd.DatetimeIndex
    assets: tuple[_Asset, ...]  # the watchlist in its order, then the safe asset when it is not in it
    ranked: int  # the first `ranked` assets are the watchlist
    safe: int | None  # the safe asset's position in `assets`; None for cash
    closes: np.ndarray  # days x assets: each asset's last close at or before the day; NaN before its first bar

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(asset.ticker for asset in self.assets)

    def ordered(self, trades: Iterable[PortfolioTrade]) -> tuple[PortfolioTrade, ...]:
        """Holdings by entry date, then asset order."""
        order = {name: position for position, name in enumerate(self.names)}
        return tuple(sorted(trades, key=lambda item: (item.trade.entry_date, order[item.ticker])))


def prepare(
    frames: Mapping[str, pd.DataFrame],
    config: BacktestConfig,
    rotation: RotationConfig,
    ranking: PriorityRule,
    weighting: WeightRule,
    safe_frame: pd.DataFrame | None = None,
) -> RotationSetup:
    """Scores every bar once. A safe asset without bars leaves its share in cash."""
    if not frames:
        raise ValueError("A rotation needs at least one ticker with bars")
    if ranking.needs_scan:
        raise ValueError(f"A rotation cannot rank by the {ranking.name} rule, which reads the scanner's score")
    extra = {}
    safe_name = rotation.safe_asset
    if safe_name is not None and safe_name not in frames and safe_frame is not None and len(safe_frame):
        extra[safe_name] = safe_frame
    every = {**frames, **extra}
    calendar = shared_calendar(every.values())
    bars = [Bars.from_frame(df, config.atr_period) for df in every.values()]
    days = [calendar.get_indexer(df.index) for df in every.values()]
    ranked = len(frames)
    scores = ranking.scores(
        PriorityInputs(tuple(frames), tuple(bars[:ranked]), tuple(days[:ranked]), calendar, Direction.LONG)
    )
    absolute = MomentumPriority(lookback=rotation.absolute_lookback, skip=0) if rotation.checks_momentum else None
    assets = tuple(
        _Asset(
            ticker=ticker,
            bars=ticker_bars,
            days=ticker_days,
            scores=scores[position] if position < ranked else np.full(len(ticker_bars), np.nan),
            weights=weighting.raw(ticker_bars),
            momentum=absolute.strength(ticker_bars) if absolute else np.full(len(ticker_bars), np.nan),
        )
        for position, (ticker, ticker_bars, ticker_days) in enumerate(zip(every, bars, days, strict=True))
    )
    closes = np.full((len(calendar), len(assets)), np.nan)
    for position, asset in enumerate(assets):
        closes[asset.days, position] = asset.bars.close
    closes = pd.DataFrame(closes).ffill().to_numpy()
    names = list(every)
    safe = names.index(safe_name) if safe_name in every else None
    return RotationSetup(calendar, assets, ranked, safe, closes)


@dataclass(frozen=True)
class _Candidate:
    position: int
    score: float
    weight: float
    momentum: float


def targets(setup: RotationSetup, rotation: RotationConfig, day: int) -> Targets:
    """The picks at the close of calendar day `day` and each asset's share of equity."""
    candidates = []
    for position, asset in enumerate(setup.assets[: setup.ranked]):
        bar = asset.last_bar(day)
        if not asset.trading(bar, day):
            continue
        candidate = _Candidate(
            position, float(asset.scores[bar]), float(asset.weights[bar]), float(asset.momentum[bar])
        )
        if math.isnan(candidate.score) or math.isnan(candidate.weight):
            continue
        if rotation.checks_momentum and math.isnan(candidate.momentum):
            continue
        candidates.append(candidate)
    chosen = sorted(candidates, key=lambda item: (-item.score, item.position))[: rotation.holdings]
    shares = book_weights(np.array([item.weight for item in chosen]), rotation.holdings) if chosen else np.array([])

    weights: dict[int, float] = {}
    picks = []
    failed = 0.0
    for candidate, share in zip(chosen, shares, strict=True):
        held = not rotation.checks_momentum or candidate.momentum > 0
        if held:
            weights[candidate.position] = weights.get(candidate.position, 0.0) + float(share)
        else:
            failed += float(share)
        picks.append(
            Pick(
                ticker=setup.assets[candidate.position].ticker,
                score=candidate.score,
                momentum=candidate.momentum if rotation.checks_momentum else math.nan,
                weight_pct=float(share) * 100.0,
                held=held,
            )
        )
    safe_share = 0.0
    if failed and setup.safe is not None and not math.isnan(setup.closes[day, setup.safe]):
        safe_share = failed
        weights[setup.safe] = weights.get(setup.safe, 0.0) + failed
    return Targets(
        date=setup.calendar[day],
        picks=tuple(picks),
        safe_pct=safe_share * 100.0,
        cash_pct=round((1.0 - sum(weights.values())) * 100.0, 10),
        weights=weights,
    )


def _lots(shares: float, lot_size: float) -> float:
    return round(math.floor(shares / lot_size + EPSILON) * lot_size, 10)


def rebalance_orders(
    setup: RotationSetup, chosen: Targets, day: int, held: np.ndarray, equity: float, lot_size: float
) -> dict[int, float]:
    """The shares each asset buys (positive) or sells (negative) at a rebalance at the close of calendar day `day`, by
    asset position, from the shares `held` and the equity marked to market at that close.

    What a ticker whose bars have ended holds cannot be sold, so the rest of the equity is shared out, and an asset
    without a bar after `day` gets no order."""
    assets = setup.assets
    owned = np.flatnonzero(np.abs(held) > EPSILON).tolist()
    ended = [position for position in owned if assets[position].last_bar(day) + 1 >= len(assets[position].bars)]
    investable = equity - sum(held[position] * setup.closes[day, position] for position in ended)
    orders: dict[int, float] = {}
    for position in sorted(set(owned) | set(chosen.weights)):
        asset, close = assets[position], setup.closes[day, position]
        weight = chosen.weights.get(position, 0.0)
        target = _lots(weight * investable / close, lot_size) if weight > 0 and close > 0 else 0.0
        delta = round(target - held[position], 10)
        if abs(delta) < EPSILON or asset.last_bar(day) + 1 >= len(asset.bars):
            continue
        orders[position] = delta
    return orders


@dataclass
class Holding:
    """One asset's shares from the buy that opens a position to the sale that empties it, with every fill's costs."""

    signal_date: pd.Timestamp  # the rebalance that opened it
    entry_date: pd.Timestamp
    shares: float = 0.0
    largest: float = 0.0
    bought: float = 0.0
    cost: float = 0.0
    sold: float = 0.0
    proceeds: float = 0.0
    fees: float = 0.0

    @property
    def empty(self) -> bool:
        return abs(self.shares) < EPSILON

    def fill(self, shares: float, price: float, fee: float) -> None:
        if shares > 0:
            self.bought += shares
            self.cost += shares * price
        else:
            self.sold -= shares
            self.proceeds -= shares * price
        self.shares = round(self.shares + shares, 10)
        self.largest = max(self.largest, self.shares)
        self.fees += fee

    def trade(self, exit_date: pd.Timestamp, mark: float | None = None) -> Trade:
        """The closed holding, or with `mark` the open one valued at that price, without an exit commission."""
        sold, proceeds = self.sold, self.proceeds
        if mark is not None:
            sold, proceeds = sold + self.shares, proceeds + self.shares * mark
        return Trade(
            direction=Direction.LONG,
            signal_date=self.signal_date,
            entry_date=self.entry_date,
            exit_date=exit_date,
            entry_price=self.cost / self.bought,
            exit_price=proceeds / sold if sold else math.nan,
            size=self.largest,
            pnl=proceeds - self.cost - self.fees,
            r_multiple=math.nan,
            exit_reason=ExitReason.OPEN if mark is not None else ExitReason.REBALANCE,
        )


def start_day(calendar: pd.DatetimeIndex, first: int | None, start: pd.Timestamp | None) -> int:
    """Where a run's series start: at its first rebalance with a pick. Without one, the run is flat from `start` on,
    or over the whole calendar."""
    if first is not None:
        return first
    if start is None:
        return 0
    return min(int(calendar.searchsorted(start)), len(calendar) - 1)


def percent_of_equity(values: np.ndarray, equity: np.ndarray) -> np.ndarray:
    """`values` in % of the equity at each close; NaN where the equity is not positive."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(equity > 0, values / equity * 100.0, np.nan)


class VectorizedRotationEngine:
    name = "vectorized"

    def run(
        self,
        frames: Mapping[str, pd.DataFrame],
        config: BacktestConfig,
        rotation: RotationConfig,
        ranking: PriorityRule,
        weighting: WeightRule,
        safe_frame: pd.DataFrame | None = None,
        start: pd.Timestamp | None = None,
    ) -> RotationResult:
        setup = prepare(frames, config, rotation, ranking, weighting, safe_frame)
        fills = FillModel(config.slippage_pct / 100.0)
        commission = config.commission_pct / 100.0
        calendar, assets = setup.calendar, setup.assets
        days = len(calendar)
        share_changes = np.zeros((days, len(assets)))
        cash_flows = np.zeros(days)
        shares = np.zeros(len(assets))
        cash = config.initial_equity
        open_holdings: dict[int, Holding] = {}
        trades: list[PortfolioTrade] = []

        schedule = rebalance_days(calendar, rotation.rebalance, start)
        first: int | None = None
        rebalances = orders = unfilled = 0
        traded_value = commissions = 0.0
        for number, day in enumerate(schedule):
            chosen = targets(setup, rotation, day)
            if first is None and not chosen.picks:
                continue  # the lookbacks are still warming up
            first = day if first is None else first
            rebalances += 1
            deadline = schedule[number + 1] if number + 1 < len(schedule) else days - 1
            owned = np.flatnonzero(shares)
            equity = cash + float(np.dot(shares[owned], setup.closes[day, owned]))
            for position, delta in rebalance_orders(setup, chosen, day, shares, equity, config.lot_size).items():
                asset = assets[position]
                bar = asset.last_bar(day) + 1
                if asset.days[bar] > deadline:
                    unfilled += 1
                    continue
                bars = asset.bars
                side = 1.0 if delta > 0 else -1.0
                price = fills.market(side, bars.open[bar], bars.high[bar], bars.low[bar])
                fee = commission * abs(delta) * price
                fill_day = int(asset.days[bar])
                share_changes[fill_day, position] += delta
                cash_flows[fill_day] -= delta * price + fee
                cash -= delta * price + fee
                shares[position] = round(shares[position] + delta, 10)
                orders += 1
                traded_value += abs(delta) * price
                commissions += fee

                holding = open_holdings.get(position)
                if holding is None:
                    holding = open_holdings[position] = Holding(calendar[day], bars.dates[bar])
                holding.fill(delta, price, fee)
                if holding.empty:
                    trades.append(PortfolioTrade(asset.ticker, holding.trade(bars.dates[bar])))
                    del open_holdings[position]

        last = days - 1
        for position, holding in open_holdings.items():
            asset = assets[position]
            trades.append(
                PortfolioTrade(
                    asset.ticker, holding.trade(asset.bars.dates[asset.last_bar(last)], setup.closes[last, position])
                )
            )

        held = np.cumsum(share_changes, axis=0)
        values = held * np.nan_to_num(setup.closes)
        equity_values = config.initial_equity + np.cumsum(cash_flows) + values.sum(axis=1)
        begin = start_day(calendar, first, start)
        index = calendar[begin:]
        safe_values = values[:, setup.safe] if setup.safe is not None else np.zeros(days)
        exposure = percent_of_equity(np.abs(values).sum(axis=1), equity_values)
        safe_pct = percent_of_equity(safe_values, equity_values)
        return RotationResult(
            engine=self.name,
            tickers=setup.names,
            equity=pd.Series(equity_values[begin:], index=index, name="equity"),
            holdings=pd.Series((np.abs(held) > EPSILON).sum(axis=1)[begin:], index=index, name="holdings"),
            exposure_pct=pd.Series(exposure[begin:], index=index, name="exposure_pct"),
            safe_pct=pd.Series(safe_pct[begin:], index=index, name="safe_pct"),
            trades=setup.ordered(trades),
            rebalances=rebalances,
            orders=orders,
            unfilled=unfilled,
            traded_value=traded_value,
            commissions=commissions,
            targets=targets(setup, rotation, last),
        )


@dataclass(frozen=True)
class RotationPeriods:
    in_sample: RotationResult  # on the bars before the split
    out_of_sample: RotationResult  # on the full history, rebalancing from the split on with fresh equity


def run_rotation_periods(
    engine: RotationEngine,
    frames: Mapping[str, pd.DataFrame],
    config: BacktestConfig,
    rotation: RotationConfig,
    ranking: PriorityRule,
    weighting: WeightRule,
    safe_frame: pd.DataFrame | None,
    split: pd.Timestamp,
) -> RotationPeriods:
    """The in-sample run only gets the bars before `split`, the out-of-sample run all bars, with fresh equity and
    rebalances from the split on, so its lookbacks are warm."""
    early = {ticker: df.loc[df.index < split] for ticker, df in frames.items()}
    early_safe = safe_frame.loc[safe_frame.index < split] if safe_frame is not None else None
    return RotationPeriods(
        in_sample=engine.run(
            {ticker: df for ticker, df in early.items() if len(df)}, config, rotation, ranking, weighting, early_safe
        ),
        out_of_sample=engine.run(frames, config, rotation, ranking, weighting, safe_frame, start=split),
    )
