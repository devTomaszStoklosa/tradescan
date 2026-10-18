"""Pyramiding: Turtle-style adds to a position that moves in the trade's favour.

Once the first unit fills, a stop order for one more unit waits at every close `add_every_atr` ATRs beyond the
previous unit's fill, until the position holds `max_units` units. The ATR is the signal bar's, the one that sized
the first unit, so the units stay evenly spaced. Every add is the size of the first unit. After an add fills, the
stop of the whole position moves to the initial stop's distance (`atr_mult` ATRs) from that fill; combined with
the other exit orders, the tightest stop wins. The exit rules apply to the whole position and measure from the
first unit. On a bar where the position exits, no unit is added.

Both engines ask a position's `Units` the same questions at every close: which add order waits for the next bar
(`add_level`) and which stop the adds ask for (`orders`, an exit tracker). They report every add with `add`.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradescan.backtest.base import BacktestConfig, ExitReason
from tradescan.backtest.exits import NO_ORDERS, ExitOrders, OpenTrade


@dataclass(frozen=True)
class Pyramiding:
    max_units: int = 1  # the first entry plus the adds; 1 adds nothing
    add_every_atr: float = 0.5

    @classmethod
    def of(cls, config: BacktestConfig) -> Pyramiding:
        return cls(max_units=config.max_units, add_every_atr=config.add_every_atr)

    @property
    def enabled(self) -> bool:
        return self.max_units > 1

    def start(self, trade: OpenTrade, atr: float) -> Units:
        """The units of a position whose first unit just filled; `atr` is the signal bar's."""
        return Units(trade.direction.sign, trade.entry_price, self.add_every_atr * atr, trade.risk, self.max_units)


class Units:
    """The units of one open position: the first fill and the adds that followed it."""

    def __init__(self, sign: float, first_fill: float, step: float, risk: float, max_units: int) -> None:
        self._sign, self._step, self._risk, self._max_units = sign, step, risk, max_units
        self._last_fill = first_fill
        self._stop: float | None = None  # where the adds moved the stop; None before the first add
        self.adds: list[tuple[int, float]] = []  # (bar, price) of every add

    @property
    def count(self) -> int:
        return 1 + len(self.adds)

    def add_level(self) -> float | None:
        """The price of the stop order for the next unit, checked on the bar after the current close; None when the
        position is full."""
        if self.count >= self._max_units:
            return None
        return self._last_fill + self._sign * self._step

    def add(self, index: int, price: float) -> None:
        """An add filled at `price` on bar `index`: the stop moves to the initial stop's distance from it."""
        self.adds.append((index, price))
        self._last_fill = price
        self._stop = price - self._sign * self._risk

    def orders(self, index: int) -> ExitOrders:
        return NO_ORDERS if self._stop is None else ExitOrders(stop=self._stop, stop_reason=ExitReason.STOP)
