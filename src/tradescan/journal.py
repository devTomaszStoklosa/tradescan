"""The trade journal: real trades with their notes and the pinned run that suggested them.

A trade is open until it has an exit date and price. Its profit is in the ticker's currency, so the summary
adds up R multiples and percentages only: a sum of dollars and zlotys would mean nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from tradescan.signals.base import Direction


@dataclass(frozen=True)
class SuggestedBy:
    """A copy of the pinned run that suggested a trade, as the UI stored it, so unpinning the run keeps it."""

    format: int  # the UI's runs-file version the snapshot was written in
    snapshot: dict[str, Any]


@dataclass(frozen=True)
class TradeEntry:
    """A trade as it was logged. Prices are per unit; fees are the trade's total, entry and exit together."""

    ticker: str
    direction: Direction
    opened: date
    entry_price: float
    quantity: float
    stop: float | None = None  # the initial stop, which sets the risk of 1R
    closed: date | None = None
    exit_price: float | None = None
    fees: float = 0.0
    notes: str = ""
    run: SuggestedBy | None = None

    def __post_init__(self) -> None:
        if not self.ticker.strip():
            raise ValueError("A trade needs a ticker")
        if self.entry_price <= 0 or self.quantity <= 0:
            raise ValueError("The entry price and the quantity must be above 0")
        if self.fees < 0:
            raise ValueError("Fees cannot be negative")
        if self.stop is not None and self.direction.sign * (self.entry_price - self.stop) <= 0:
            side = "below" if self.direction is Direction.LONG else "above"
            raise ValueError(f"The stop of a {self.direction} trade must be {side} the entry price")
        if (self.closed is None) != (self.exit_price is None):
            raise ValueError("An exit needs both its date and its price")
        if self.exit_price is not None and self.exit_price <= 0:
            raise ValueError("The exit price must be above 0")
        if self.closed is not None and self.closed < self.opened:
            raise ValueError("A trade cannot close before it opened")

    @property
    def is_open(self) -> bool:
        return self.exit_price is None

    @property
    def risk(self) -> float | None:
        """What the initial stop put at risk; None without a stop."""
        return None if self.stop is None else abs(self.entry_price - self.stop) * self.quantity

    @property
    def profit(self) -> float | None:
        """Profit after fees; None while the trade is open."""
        if self.exit_price is None:
            return None
        return self.direction.sign * (self.exit_price - self.entry_price) * self.quantity - self.fees

    @property
    def return_pct(self) -> float | None:
        """Profit after fees as a percent of the position's value at the entry."""
        profit = self.profit
        return None if profit is None else profit / (self.entry_price * self.quantity) * 100.0

    @property
    def r_multiple(self) -> float | None:
        """Profit after fees in units of the initial risk; None while open or without a stop."""
        profit, risk = self.profit, self.risk
        return None if profit is None or risk is None else profit / risk


@dataclass(frozen=True)
class JournalTrade:
    id: int
    entry: TradeEntry
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class JournalSummary:
    open_trades: int
    closed_trades: int
    win_rate_pct: float | None  # closed trades with a profit after fees
    average_return_pct: float | None
    r_trades: int  # closed trades with a stop, which have an R multiple
    average_r: float | None
    total_r: float | None


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(entries: Sequence[TradeEntry]) -> JournalSummary:
    closed = [entry for entry in entries if not entry.is_open]
    profits = [entry.profit for entry in closed if entry.profit is not None]
    returns = [entry.return_pct for entry in closed if entry.return_pct is not None]
    multiples = [entry.r_multiple for entry in closed if entry.r_multiple is not None]
    return JournalSummary(
        open_trades=len(entries) - len(closed),
        closed_trades=len(closed),
        win_rate_pct=sum(profit > 0 for profit in profits) / len(profits) * 100.0 if profits else None,
        average_return_pct=_mean(returns),
        r_trades=len(multiples),
        average_r=_mean(multiples),
        total_r=sum(multiples) if multiples else None,
    )
