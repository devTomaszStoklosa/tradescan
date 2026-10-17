"""Portfolio backtest: one setup on many tickers that share one equity.

Every ticker trades by the rules of a single-ticker backtest (see `base`): its signals, entry filters, entry
rule and exit rules, executed on its own bars. The portfolio decides at each close of the shared calendar, the
union of every ticker's dates, which of the signals that fired on free tickers get an entry order and at what
size (`allocation.allocate`), with the equity marked to market at each ticker's last close.

A ticker is busy, and ignores its signals, while its entry order waits or its position is open. An order holds
its slot until it fills or expires, a position until the close of its exit bar. A ticker whose bars end before
the calendar does keeps a position that is still open, marked to its last close, until the end.

Both portfolio engines prepare the tickers with `prepare`, which also has the priority rule score every ticker at
once, and allocate with `allocate`; only the order execution differs between them, as for the single-ticker
engines.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import reduce
from typing import Protocol

import numpy as np
import pandas as pd

from tradescan.backtest.allocation import Candidate, PortfolioConfig, allocate
from tradescan.backtest.base import BacktestConfig, ExitReason, Trade
from tradescan.backtest.exits import OpenTrade
from tradescan.backtest.oos import SignalSince
from tradescan.backtest.priority import PriorityInputs, PriorityRule
from tradescan.backtest.rules import Bars
from tradescan.backtest.trade_rules import PreparedRules, TradeRules
from tradescan.backtest.vectorized import FillModel, find_entry, find_exit, pnl_path
from tradescan.signals.base import Direction, Signal


@dataclass(frozen=True)
class PortfolioTrade:
    ticker: str
    trade: Trade


@dataclass(frozen=True)
class PortfolioResult:
    engine: str
    signal: str
    tickers: tuple[str, ...]  # in watchlist order
    equity: pd.Series  # at each close of the shared calendar
    positions: pd.Series  # open positions at each close
    exposure_pct: pd.Series  # gross value of the open positions at each close, % of equity
    trades: tuple[PortfolioTrade, ...]  # by entry date, then watchlist order
    orders: int  # entry orders placed
    no_slot: int  # signals skipped because every slot was taken
    no_room: int  # signals skipped because less than one lot fitted under the exposure cap


class PortfolioEngine(Protocol):
    name: str

    def run(
        self,
        frames: Mapping[str, pd.DataFrame],
        signal: Signal,
        config: BacktestConfig,
        rules: TradeRules,
        portfolio: PortfolioConfig,
        priority: PriorityRule,
    ) -> PortfolioResult:
        """`frames` holds each ticker's bars on its own dates, in watchlist order."""
        ...


def shared_calendar(frames: Iterable[pd.DataFrame]) -> pd.DatetimeIndex:
    """Every date on which at least one ticker has a bar."""
    return reduce(lambda calendar, df: calendar.union(df.index), frames, pd.DatetimeIndex([], name="date"))


@dataclass(frozen=True, eq=False)
class TickerSetup:
    """One ticker's bars, signals, rules and priority scores, prepared once per run."""

    ticker: str
    bars: Bars
    events: np.ndarray
    rules: PreparedRules
    scores: np.ndarray
    days: np.ndarray  # the position of each bar in the shared calendar

    def last_bar(self, day: int) -> int:
        """The ticker's last bar at or before calendar day `day`; -1 before its first bar."""
        return int(np.searchsorted(self.days, day, side="right")) - 1


@dataclass(frozen=True, eq=False)
class PortfolioSetup:
    calendar: pd.DatetimeIndex
    tickers: tuple[TickerSetup, ...]  # in watchlist order
    direction: Direction

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(ticker.ticker for ticker in self.tickers)

    def signals_by_day(self) -> list[list[tuple[int, int]]]:
        """For each calendar day, the (ticker position, bar) of every signal at that close, in watchlist order."""
        by_day: list[list[tuple[int, int]]] = [[] for _ in range(len(self.calendar))]
        for position, ticker in enumerate(self.tickers):
            for index in np.flatnonzero(ticker.events):
                by_day[ticker.days[index]].append((position, int(index)))
        return by_day

    def ordered(self, trades: Iterable[PortfolioTrade]) -> tuple[PortfolioTrade, ...]:
        """Trades by entry date, then watchlist order."""
        order = {name: position for position, name in enumerate(self.names)}
        return tuple(sorted(trades, key=lambda item: (item.trade.entry_date, order[item.ticker])))


def prepare(
    frames: Mapping[str, pd.DataFrame], signal: Signal, config: BacktestConfig, rules: TradeRules, priority: PriorityRule
) -> PortfolioSetup:
    if not frames:
        raise ValueError("A portfolio backtest needs at least one ticker with bars")
    calendar = shared_calendar(frames.values())
    bars = tuple(Bars.from_frame(df, config.atr_period) for df in frames.values())
    days = tuple(calendar.get_indexer(df.index) for df in frames.values())
    scores = priority.scores(PriorityInputs(tuple(frames), bars, days, calendar, signal.direction))
    tickers = tuple(
        TickerSetup(
            ticker=ticker,
            bars=ticker_bars,
            events=signal.events(df).to_numpy(dtype=bool),
            rules=rules.prepare(ticker_bars, signal.direction),
            scores=ticker_scores,
            days=ticker_days,
        )
        for (ticker, df), ticker_bars, ticker_days, ticker_scores in zip(frames.items(), bars, days, scores, strict=True)
    )
    return PortfolioSetup(calendar, tickers, signal.direction)


@dataclass(frozen=True)
class _Slot:
    """A busy ticker: its entry order waiting to fill, then the position the order opened."""

    size: float
    reference: float
    filled: int | None  # the calendar day of the entry fill; None for an order that expires unfilled
    release: int  # the calendar day at whose close the ticker is free again; the calendar's length for never


class VectorizedPortfolioEngine:
    name = "vectorized"

    def run(
        self,
        frames: Mapping[str, pd.DataFrame],
        signal: Signal,
        config: BacktestConfig,
        rules: TradeRules,
        portfolio: PortfolioConfig,
        priority: PriorityRule,
    ) -> PortfolioResult:
        setup = prepare(frames, signal, config, rules, priority)
        fills = FillModel(config.slippage_pct / 100.0)
        commission = config.commission_pct / 100.0
        sign = setup.direction.sign
        days = len(setup.calendar)
        daily_pnl = np.zeros(days)
        positions = np.zeros(days, dtype=int)
        exposure = np.zeros(days)
        trades: list[PortfolioTrade] = []

        def place(candidate: Candidate) -> _Slot:
            ticker, plan, index = setup.tickers[candidate.ticker], candidate.plan, candidate.index
            bars = ticker.bars
            entry = find_entry(bars, index, plan, fills, sign)
            if entry is None:
                expiry = index + plan.valid_bars  # a signal on the bar the order expires may place a new one
                return _Slot(plan.size, plan.reference, None, int(ticker.days[expiry]) if expiry < len(bars) else days)
            entry_index, entry_price = entry
            trade = OpenTrade(setup.direction, entry_index, entry_price, plan.reference, plan.stop, plan.risk)
            exit_ = find_exit(bars, ticker.rules.track(trade), entry_index, fills, sign)
            path, pnl = pnl_path(bars.close, entry_index, entry_price, exit_, plan.size, sign, commission)
            daily_pnl[ticker.days[entry_index : exit_.index + 1]] += path
            trades.append(
                PortfolioTrade(
                    ticker.ticker,
                    Trade(
                        direction=setup.direction,
                        signal_date=bars.dates[index],
                        entry_date=bars.dates[entry_index],
                        exit_date=bars.dates[exit_.index],
                        entry_price=entry_price,
                        exit_price=exit_.price,
                        size=plan.size,
                        pnl=pnl,
                        r_multiple=pnl / (plan.size * plan.risk),
                        exit_reason=exit_.reason,
                    ),
                )
            )
            release = int(ticker.days[exit_.index]) if exit_.reason != ExitReason.OPEN else days
            return _Slot(plan.size, plan.reference, int(ticker.days[entry_index]), release)

        slots: dict[int, _Slot] = {}
        orders = no_slot = no_room = 0
        equity = config.initial_equity
        for day, signals in enumerate(setup.signals_by_day()):
            equity += daily_pnl[day]  # trades are booked when placed, and only ever on later days
            slots = {position: slot for position, slot in slots.items() if slot.release > day}
            open_value = waiting_value = 0.0
            for position, slot in slots.items():
                if slot.filled is not None and slot.filled <= day:
                    ticker = setup.tickers[position]
                    open_value += slot.size * ticker.bars.close[ticker.last_bar(day)]
                    positions[day] += 1
                else:
                    waiting_value += slot.size * slot.reference
            exposure[day] = open_value / equity * 100.0 if equity > 0 else np.nan

            candidates = []
            for position, index in signals:
                ticker = setup.tickers[position]
                if position in slots or index + 1 >= len(ticker.bars):
                    continue
                plan = ticker.rules.plan(index, equity, config)
                if plan is not None:
                    candidates.append(Candidate(position, index, float(ticker.scores[index]), plan))
            allocation = allocate(candidates, len(slots), open_value + waiting_value, equity, portfolio, config.lot_size)
            orders += len(allocation.accepted)
            no_slot += allocation.no_slot
            no_room += allocation.no_room
            for candidate in allocation.accepted:
                slots[candidate.ticker] = place(candidate)

        calendar = setup.calendar
        return PortfolioResult(
            engine=self.name,
            signal=signal.name,
            tickers=setup.names,
            equity=pd.Series(config.initial_equity + np.cumsum(daily_pnl), index=calendar, name="equity"),
            positions=pd.Series(positions, index=calendar, name="positions"),
            exposure_pct=pd.Series(exposure, index=calendar, name="exposure_pct"),
            trades=setup.ordered(trades),
            orders=orders,
            no_slot=no_slot,
            no_room=no_room,
        )


@dataclass(frozen=True)
class PortfolioPeriods:
    in_sample: PortfolioResult  # on the bars before the split
    out_of_sample: PortfolioResult  # on the full history, with signals from the split on only


def run_portfolio_periods(
    engine: PortfolioEngine,
    frames: Mapping[str, pd.DataFrame],
    signal: Signal,
    config: BacktestConfig,
    rules: TradeRules,
    portfolio: PortfolioConfig,
    priority: PriorityRule,
    split: pd.Timestamp,
) -> PortfolioPeriods:
    """The in-sample and the out-of-sample run, split at the calendar date `split`, the way `oos` splits one
    ticker: the in-sample run only gets the bars before it, the out-of-sample run all bars, with fresh equity and
    signals from the split on."""
    early = {ticker: df.loc[df.index < split] for ticker, df in frames.items()}
    return PortfolioPeriods(
        in_sample=engine.run({ticker: df for ticker, df in early.items() if len(df)}, signal, config, rules, portfolio, priority),
        out_of_sample=engine.run(frames, SignalSince(signal, split), config, rules, portfolio, priority),
    )
