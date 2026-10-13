"""ATR-based trade levels and fixed-fractional position sizing.

The scanner's risk plan and both backtest engines use these functions, so all three agree.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from tradescan.signals.base import Direction


def trade_levels(
    direction: Direction,
    reference: float,
    atr: float,
    atr_mult: float,
    targets_r: Sequence[float],
) -> tuple[float, tuple[float, ...], float]:
    """Return (stop, targets, risk per share) around `reference`, with the stop `atr_mult` ATRs away."""
    risk_per_share = atr_mult * atr
    stop = reference - direction.sign * risk_per_share
    targets = tuple(reference + direction.sign * multiple * risk_per_share for multiple in targets_r)
    return stop, targets, risk_per_share


def position_size(
    equity: float,
    price: float,
    risk_per_share: float,
    risk_pct: float,
    max_position_pct: float,
    lot_size: float = 1.0,
) -> float:
    """Size that loses `risk_pct` of equity at the stop, capped at `max_position_pct` of equity in value."""
    if equity <= 0 or price <= 0 or not risk_per_share > 0 or lot_size <= 0:
        return 0.0
    by_risk = equity * risk_pct / 100.0 / risk_per_share
    by_value = equity * max_position_pct / 100.0 / price
    lots = math.floor(min(by_risk, by_value) / lot_size + 1e-9)
    return round(lots * lot_size, 10)


@dataclass(frozen=True)
class RiskPlan:
    entry: float
    stop: float
    targets: tuple[float, ...]
    risk_per_share: float
    size: float

    @property
    def position_value(self) -> float:
        return self.entry * self.size

    @property
    def risk_amount(self) -> float:
        return self.risk_per_share * self.size


class RiskPlanner:
    def __init__(
        self,
        equity: float,
        risk_pct: float,
        max_position_pct: float,
        atr_mult: float,
        targets_r: Sequence[float],
        lot_size: float = 1.0,
    ) -> None:
        self._equity = equity
        self._risk_pct = risk_pct
        self._max_position_pct = max_position_pct
        self._atr_mult = atr_mult
        self._targets_r = tuple(targets_r)
        self._lot_size = lot_size

    def plan(self, direction: Direction, entry: float, atr: float) -> RiskPlan:
        stop, targets, risk_per_share = trade_levels(direction, entry, atr, self._atr_mult, self._targets_r)
        size = position_size(
            self._equity, entry, risk_per_share, self._risk_pct, self._max_position_pct, self._lot_size
        )
        return RiskPlan(entry=entry, stop=stop, targets=targets, risk_per_share=risk_per_share, size=size)
