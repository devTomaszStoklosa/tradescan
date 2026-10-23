"""Portfolio backtest: one setup on many tickers that share one equity.

Every ticker trades by the rules of a single-ticker backtest (see `base`): its signals, entry filters, entry
rule and exit rules, executed on its own bars. The portfolio decides at each close of the shared calendar, the
union of every ticker's dates, which of the signals that fired on free tickers get an entry order and at what
size (`allocation.allocate`), with the equity marked to market at each ticker's last close.

With pyramiding (`max_units` above 1), the position of a busy ticker adds units by the stop orders of `pyramid`. An
add takes no slot. Its order counts against `max_exposure_pct` like a waiting entry order, at its value at the add
level; at each close the adds are decided before the new signals, in watchlist order, each all or nothing: without
room under the cap there is no add order until the next close.

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
from tradescan.backtest.base import BacktestConfig, ExitReason, Fill, Trade
from tradescan.backtest.exits import OpenTrade
from tradescan.backtest.oos import SignalSince
from tradescan.backtest.priority import PriorityInputs, PriorityRule
from tradescan.backtest.pyramid import Pyramiding
from tradescan.backtest.rules import Bars
from tradescan.backtest.trade_rules import EntryPlan, PreparedRules, TradeRules
from tradescan.backtest.vectorized import FillModel, TradeExit, fill_on_bar
from tradescan.data.schema import bar_dates
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
    no_room_adds: int = 0  # closes at which a position's next unit was not ordered for want of room under the cap


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
    return reduce(lambda calendar, df: calendar.union(bar_dates(df)), frames, pd.DatetimeIndex([], name="date"))


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
    frames: Mapping[str, pd.DataFrame],
    signal: Signal,
    config: BacktestConfig,
    rules: TradeRules,
    priority: PriorityRule,
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
        for (ticker, df), ticker_bars, ticker_days, ticker_scores in zip(
            frames.items(), bars, days, scores, strict=True
        )
    )
    return PortfolioSetup(calendar, tickers, signal.direction)


@dataclass(frozen=True)
class _Waiting:
    """A busy ticker whose entry order waits to fill, placed at the close of bar `index`."""

    index: int
    plan: EntryPlan


class _Position:
    """A busy ticker's open position: the first unit and the adds that followed it. `step` moves it over one bar of
    the ticker, booking that bar's P&L the way `pnl_path` books a unit's."""

    def __init__(
        self,
        ticker: TickerSetup,
        direction: Direction,
        signal_index: int,
        plan: EntryPlan,
        entry: tuple[int, float],
        pyramid: Pyramiding,
    ) -> None:
        entry_index, entry_price = entry
        self.ticker, self.direction, self.signal_index, self.plan = ticker, direction, signal_index, plan
        trade = OpenTrade(direction, entry_index, entry_price, plan.reference, plan.stop, plan.risk)
        self.units = pyramid.start(trade, plan.atr) if pyramid.enabled else None
        self.tracker = ticker.rules.track(trade, (self.units,) if self.units is not None else ())
        self.fills = [(entry_index, entry_price)]
        self.bar = entry_index
        self.armed = False  # the stop order for the next unit waits, with its value counted in the exposure
        self.close_bar()

    @property
    def size(self) -> float:
        return self.plan.size * len(self.fills)

    @property
    def armed_value(self) -> float:
        return self.plan.size * self.add if self.armed and self.add is not None else 0.0

    def close_bar(self) -> None:
        """The orders this close places for the next bar; the portfolio arms the add order if it fits."""
        self.orders = self.tracker.orders(self.bar)
        self.add = self.units.add_level() if self.units is not None else None
        self.armed = False

    def entry_pnl(self, commission: float) -> float:
        """The P&L of the entry bar, booked when the entry fills."""
        (index, price), sign, size = self.fills[0], self.direction.sign, self.plan.size
        return sign * size * (self.ticker.bars.close[index] - price) - commission * price * size

    def step(self, bar: int, fills: FillModel, commission: float) -> tuple[float, TradeExit | None]:
        """The position over `bar`: its P&L on the bar and the exit, if the position leaves on it."""
        bars, sign, size = self.ticker.bars, self.direction.sign, self.plan.size
        exit_, add_price = fill_on_bar(bars, self.orders, self.add if self.armed else None, bar, fills, sign)
        previous = bars.close[self.bar]
        units = len(self.fills)
        if exit_ is not None:
            return units * (sign * size * (exit_.price - previous) - commission * exit_.price * size), exit_
        pnl = units * sign * size * (bars.close[bar] - previous)
        if add_price is not None and self.units is not None:
            self.units.add(bar, add_price)
            self.fills.append((bar, add_price))
            pnl += sign * size * (bars.close[bar] - add_price) - commission * add_price * size
        self.bar = bar
        self.close_bar()
        return pnl, None

    def trade(self, exit_: TradeExit, commission: float) -> Trade:
        """The finished trade; with `ExitReason.OPEN`, the position is marked to the ticker's last close."""
        bars, sign, plan = self.ticker.bars, self.direction.sign, self.plan
        count = len(self.fills)
        exit_cost = commission * exit_.price * plan.size if exit_.reason != ExitReason.OPEN else 0.0
        pnl = sum(
            sign * plan.size * (exit_.price - price) - commission * price * plan.size - exit_cost
            for _, price in self.fills
        )
        return Trade(
            direction=self.direction,
            signal_date=bars.dates[self.signal_index],
            entry_date=bars.dates[self.fills[0][0]],
            exit_date=bars.dates[exit_.index],
            entry_price=sum(price for _, price in self.fills) / count,  # the units are equal in size
            exit_price=exit_.price,
            size=plan.size * count,
            pnl=pnl,
            r_multiple=pnl / (plan.size * plan.risk),
            exit_reason=exit_.reason,
            adds=tuple(Fill(bars.dates[index], price) for index, price in self.fills[1:]),
        )


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
        pyramid = Pyramiding.of(config)
        sign = setup.direction.sign
        days = len(setup.calendar)
        daily_pnl = np.zeros(days)
        positions = np.zeros(days, dtype=int)
        exposure = np.zeros(days)
        trades: list[PortfolioTrade] = []
        bar_on_day = []  # for each ticker, its bar at each calendar day; -1 on days without one
        for ticker in setup.tickers:
            on_day = np.full(days, -1)
            on_day[ticker.days] = np.arange(len(ticker.bars))
            bar_on_day.append(on_day)

        slots: dict[int, _Waiting | _Position] = {}
        orders = no_slot = no_room = no_room_adds = 0
        equity = config.initial_equity
        for day, signals in enumerate(setup.signals_by_day()):
            moved: list[int] = []  # the positions that had a bar today and are still open
            for position in sorted(slots):
                bar = int(bar_on_day[position][day])
                if bar < 0:
                    continue
                slot, ticker = slots[position], setup.tickers[position]
                if isinstance(slot, _Waiting):
                    bars = ticker.bars
                    price = fills.entry(slot.plan, sign, bars.open[bar], bars.high[bar], bars.low[bar])
                    if price is None:
                        if bar >= slot.index + slot.plan.valid_bars:  # expired: this bar's signal may order anew
                            del slots[position]
                        continue
                    held = _Position(ticker, setup.direction, slot.index, slot.plan, (bar, price), pyramid)
                    slots[position] = held
                    pnl = held.entry_pnl(commission)
                else:
                    pnl, exit_ = slot.step(bar, fills, commission)
                    if exit_ is not None:
                        daily_pnl[day] += pnl
                        equity += pnl
                        trades.append(PortfolioTrade(ticker.ticker, slot.trade(exit_, commission)))
                        del slots[position]
                        continue
                daily_pnl[day] += pnl
                equity += pnl
                moved.append(position)

            open_value = reserved = 0.0
            for position, slot in slots.items():
                if isinstance(slot, _Position):
                    ticker = setup.tickers[position]
                    open_value += slot.size * ticker.bars.close[ticker.last_bar(day)]
                    positions[day] += 1
                    if position not in moved:
                        reserved += slot.armed_value
                else:
                    reserved += slot.plan.size * slot.plan.reference
            exposure[day] = open_value / equity * 100.0 if equity > 0 else np.nan

            # Adds go before new signals: the room goes first to the positions that are already working.
            used = open_value + reserved
            limit = equity * portfolio.max_exposure_pct / 100.0
            for position in moved:
                held = slots[position]
                assert isinstance(held, _Position)
                if held.add is None:
                    continue
                value = held.plan.size * held.add
                if used + value <= limit:
                    held.armed = True
                    used += value
                else:
                    no_room_adds += 1

            candidates = []
            for position, index in signals:
                ticker = setup.tickers[position]
                if position in slots or index + 1 >= len(ticker.bars):
                    continue
                plan = ticker.rules.plan(index, equity, config)
                if plan is not None:
                    candidates.append(Candidate(position, index, float(ticker.scores[index]), plan))
            allocation = allocate(candidates, len(slots), used, equity, portfolio, config.lot_size)
            orders += len(allocation.accepted)
            no_slot += allocation.no_slot
            no_room += allocation.no_room
            for candidate in allocation.accepted:
                slots[candidate.ticker] = _Waiting(candidate.index, candidate.plan)

        for position, slot in slots.items():
            if isinstance(slot, _Position):  # still open: marked to the ticker's last close
                ticker = setup.tickers[position]
                last = TradeExit(len(ticker.bars) - 1, float(ticker.bars.close[-1]), ExitReason.OPEN)
                trades.append(PortfolioTrade(ticker.ticker, slot.trade(last, commission)))

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
            no_room_adds=no_room_adds,
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
        in_sample=engine.run(
            {ticker: df for ticker, df in early.items() if len(df)}, signal, config, rules, portfolio, priority
        ),
        out_of_sample=engine.run(frames, SignalSince(signal, split), config, rules, portfolio, priority),
    )
