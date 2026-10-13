"""Fast backtest on numpy arrays.

Signals, ATR and the daily P&L of each trade are vectorized. Only the exit search loops, because
whether the stop or the target is hit first depends on the bar-by-bar price path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradescan.backtest.base import BacktestConfig, BacktestResult, ExitReason, Trade
from tradescan.indicators import atr
from tradescan.risk import position_size, trade_levels
from tradescan.signals.base import Signal


@dataclass(frozen=True)
class _Bars:
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> _Bars:
        return cls(*(df[column].to_numpy(dtype=float) for column in ("open", "high", "low", "close")))

    def __len__(self) -> int:
        return len(self.close)


@dataclass(frozen=True)
class _FillModel:
    """Fill prices matching backtrader's percentage slippage (fills stay inside the bar's range)."""

    slippage: float
    sign: float  # +1 long, -1 short

    def entry(self, price: float, high: float, low: float) -> float:
        return float(np.clip(price * (1.0 + self.sign * self.slippage), low, high))

    def market_exit(self, price: float, high: float, low: float) -> float:
        return float(np.clip(price * (1.0 - self.sign * self.slippage), low, high))

    def limit_exit(self, price: float, limit: float) -> float:
        slipped = price * (1.0 - self.sign * self.slippage)
        return max(slipped, limit) if self.sign > 0 else min(slipped, limit)


@dataclass(frozen=True)
class _Exit:
    index: int
    price: float
    reason: str


class VectorizedEngine:
    name = "vectorized"

    def run(self, ticker: str, df: pd.DataFrame, signal: Signal, config: BacktestConfig) -> BacktestResult:
        bars = _Bars.from_frame(df)
        events = signal.events(df).to_numpy(dtype=bool)
        atr_values = atr(df, config.atr_period).to_numpy()
        sign = signal.direction.sign
        fills = _FillModel(config.slippage_pct / 100.0, sign)
        commission = config.commission_pct / 100.0

        daily_pnl = np.zeros(len(bars))
        trades: list[Trade] = []
        equity = config.initial_equity
        next_free = 0
        for signal_index in np.flatnonzero(events):
            entry_index = signal_index + 1
            if signal_index < next_free or entry_index >= len(bars) or not np.isfinite(atr_values[signal_index]):
                continue
            reference = bars.close[signal_index]
            stop, (target,), risk = trade_levels(
                signal.direction, reference, atr_values[signal_index], config.atr_mult, (config.target_r,)
            )
            size = position_size(equity, reference, risk, config.risk_pct, config.max_position_pct, config.lot_size)
            if size <= 0:
                continue

            entry_price = fills.entry(bars.open[entry_index], bars.high[entry_index], bars.low[entry_index])
            exit_ = _find_exit(bars, entry_index, stop, target, config.max_hold_bars, fills)
            pnl = _book(daily_pnl, bars.close, entry_index, entry_price, exit_, size, sign, commission)
            equity += pnl
            trades.append(
                Trade(
                    direction=signal.direction,
                    signal_date=df.index[signal_index],
                    entry_date=df.index[entry_index],
                    exit_date=df.index[exit_.index],
                    entry_price=entry_price,
                    exit_price=exit_.price,
                    size=size,
                    pnl=pnl,
                    r_multiple=pnl / (size * risk),
                    exit_reason=exit_.reason,
                )
            )
            next_free = exit_.index if exit_.reason != ExitReason.OPEN else len(bars)

        equity_curve = pd.Series(config.initial_equity + np.cumsum(daily_pnl), index=df.index, name="equity")
        return BacktestResult(engine=self.name, ticker=ticker, signal=signal.name, equity=equity_curve, trades=tuple(trades))


def _find_exit(bars: _Bars, entry_index: int, stop: float, target: float, max_hold: int, fills: _FillModel) -> _Exit:
    sign = fills.sign
    last_check = min(entry_index + max_hold - 1, len(bars) - 1)
    for i in range(entry_index + 1, last_check + 1):
        open_, high, low = bars.open[i], bars.high[i], bars.low[i]
        adverse, favorable = (low, high) if sign > 0 else (high, low)
        if sign * (open_ - stop) <= 0:
            return _Exit(i, fills.market_exit(open_, high, low), ExitReason.STOP)
        if sign * (open_ - target) >= 0:
            return _Exit(i, fills.limit_exit(open_, target), ExitReason.TARGET)
        if sign * (adverse - stop) <= 0:
            return _Exit(i, fills.market_exit(stop, high, low), ExitReason.STOP)
        if sign * (favorable - target) >= 0:
            return _Exit(i, target, ExitReason.TARGET)

    time_index = entry_index + max_hold
    if time_index < len(bars):
        price = fills.market_exit(bars.open[time_index], bars.high[time_index], bars.low[time_index])
        return _Exit(time_index, price, ExitReason.TIME)
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
