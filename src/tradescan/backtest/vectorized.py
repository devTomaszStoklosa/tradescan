"""Fast backtest on numpy arrays.

Signals, rule levels and the daily P&L of each trade are vectorized. Only the order fills loop over the
bars of a trade, because whether an order fills, and which one first, depends on the bar-by-bar path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradescan.backtest.base import BacktestConfig, BacktestResult, ExitReason, Trade
from tradescan.backtest.entries import OrderType
from tradescan.backtest.exits import ExitTracker, OpenTrade
from tradescan.backtest.rules import Bars
from tradescan.backtest.trade_rules import EntryPlan, TradeRules
from tradescan.signals.base import Signal


@dataclass(frozen=True)
class _FillModel:
    """Fill prices of backtrader's broker with percentage slippage (`set_slippage_perc` defaults).

    `side` is +1 for an order that buys and -1 for one that sells. Slippage works against the order and
    never moves a fill outside the bar's range; a limit order never fills worse than its level.
    """

    slippage: float

    def _slipped(self, price: float, side: float) -> float:
        return price * (1.0 + side * self.slippage)

    def market(self, side: float, open_: float, high: float, low: float) -> float:
        return float(np.clip(self._slipped(open_, side), low, high))

    def stop(self, side: float, level: float, open_: float, high: float, low: float) -> float | None:
        if side * (open_ - level) >= 0:  # gapped through the level
            return self.market(side, open_, high, low)
        if side * ((high if side > 0 else low) - level) >= 0:
            return float(np.clip(self._slipped(level, side), low, high))
        return None

    def limit(self, side: float, level: float, open_: float, high: float, low: float) -> float | None:
        if side * (open_ - level) <= 0:  # opened at the level or better
            slipped = self._slipped(open_, side)
            return float(min(slipped, high, level) if side > 0 else max(slipped, level))
        if side * ((low if side > 0 else high) - level) <= 0:
            return float(level)
        return None

    def entry(self, plan: EntryPlan, side: float, open_: float, high: float, low: float) -> float | None:
        if plan.type is OrderType.MARKET:
            return self.market(side, open_, high, low)
        if plan.type is OrderType.STOP:
            return self.stop(side, plan.level, open_, high, low)
        return self.limit(side, plan.level, open_, high, low)


@dataclass(frozen=True)
class _Exit:
    index: int
    price: float
    reason: str


class VectorizedEngine:
    name = "vectorized"

    def run(
        self, ticker: str, df: pd.DataFrame, signal: Signal, config: BacktestConfig, rules: TradeRules | None = None
    ) -> BacktestResult:
        bars = Bars.from_frame(df, config.atr_period)
        events = signal.events(df).to_numpy(dtype=bool)
        prepared = (rules or TradeRules()).prepare(bars, signal.direction)
        sign = signal.direction.sign
        fills = _FillModel(config.slippage_pct / 100.0)
        commission = config.commission_pct / 100.0

        daily_pnl = np.zeros(len(bars))
        trades: list[Trade] = []
        equity = config.initial_equity
        next_free = 0
        for signal_index in np.flatnonzero(events):
            if signal_index < next_free or signal_index + 1 >= len(bars):
                continue
            plan = prepared.plan(signal_index, equity, config)
            if plan is None:
                continue
            entry = _find_entry(bars, signal_index, plan, fills, sign)
            if entry is None:
                next_free = signal_index + plan.valid_bars  # a signal on the bar the order expires may place a new one
                continue

            entry_index, entry_price = entry
            trade = OpenTrade(signal.direction, entry_index, entry_price, plan.reference, plan.stop, plan.risk)
            exit_ = _find_exit(bars, prepared.track(trade), entry_index, fills, sign)
            pnl = _book(daily_pnl, bars.close, entry_index, entry_price, exit_, plan.size, sign, commission)
            equity += pnl
            trades.append(
                Trade(
                    direction=signal.direction,
                    signal_date=df.index[signal_index],
                    entry_date=df.index[entry_index],
                    exit_date=df.index[exit_.index],
                    entry_price=entry_price,
                    exit_price=exit_.price,
                    size=plan.size,
                    pnl=pnl,
                    r_multiple=pnl / (plan.size * plan.risk),
                    exit_reason=exit_.reason,
                )
            )
            next_free = exit_.index if exit_.reason != ExitReason.OPEN else len(bars)

        equity_curve = pd.Series(config.initial_equity + np.cumsum(daily_pnl), index=df.index, name="equity")
        return BacktestResult(engine=self.name, ticker=ticker, signal=signal.name, equity=equity_curve, trades=tuple(trades))


def _find_entry(bars: Bars, signal_index: int, plan: EntryPlan, fills: _FillModel, sign: float) -> tuple[int, float] | None:
    """The bar and price at which the entry order fills, or None when it expires unfilled."""
    last = min(signal_index + plan.valid_bars, len(bars) - 1)
    for i in range(signal_index + 1, last + 1):
        price = fills.entry(plan, sign, bars.open[i], bars.high[i], bars.low[i])
        if price is not None:
            return i, price
    return None


def _find_exit(bars: Bars, tracker: ExitTracker, entry_index: int, fills: _FillModel, sign: float) -> _Exit:
    """Executes the orders the tracker names at each close on the next bar, the way backtrader's broker does:
    an exit at the open first, then the stop, then the target."""
    side = -sign
    for index in range(entry_index, len(bars) - 1):
        orders = tracker.orders(index)
        bar = index + 1
        open_, high, low = bars.open[bar], bars.high[bar], bars.low[bar]
        if orders.at_open is not None:
            return _Exit(bar, fills.market(side, open_, high, low), orders.at_open)
        if orders.stop is not None and (price := fills.stop(side, orders.stop, open_, high, low)) is not None:
            return _Exit(bar, price, orders.stop_reason)
        if orders.target is not None and (price := fills.limit(side, orders.target, open_, high, low)) is not None:
            return _Exit(bar, price, orders.target_reason)
    return _Exit(len(bars) - 1, float(bars.close[-1]), ExitReason.OPEN)


def _book(
    daily_pnl: np.ndarray,
    close: np.ndarray,
    entry_index: int,
    entry_price: float,
    exit_: _Exit,
    size: float,
    sign: float,
    commission: float,
) -> float:
    """Spread the trade's mark-to-market P&L over its bars and return the net trade P&L."""
    entry_cost = commission * entry_price * size
    exit_cost = commission * exit_.price * size if exit_.reason != ExitReason.OPEN else 0.0
    exposure = sign * size
    if exit_.index == entry_index:
        daily_pnl[entry_index] += exposure * (exit_.price - entry_price) - entry_cost - exit_cost
    else:
        daily_pnl[entry_index] += exposure * (close[entry_index] - entry_price) - entry_cost
        daily_pnl[entry_index + 1 : exit_.index] += exposure * np.diff(close[entry_index : exit_.index])
        daily_pnl[exit_.index] += exposure * (exit_.price - close[exit_.index - 1]) - exit_cost
    return exposure * (exit_.price - entry_price) - entry_cost - exit_cost
