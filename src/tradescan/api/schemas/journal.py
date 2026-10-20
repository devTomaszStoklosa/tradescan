"""Models of the trade journal at /api/journal."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tradescan.api.schemas.common import RequestModel
from tradescan.signals.base import Direction


class SuggestingRun(RequestModel):
    """A copy of the pinned run that suggested a trade, so the trade keeps it after the run is unpinned."""

    format: int = Field(ge=1, description="The UI's runs-file version the snapshot was written in")
    snapshot: dict[str, Any] = Field(description="The run as the UI keeps it, its pin name included")


class JournalTradeIn(RequestModel):
    """A real trade. Prices are per unit, in the ticker's currency; an exit needs both its date and its price."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    ticker: str = Field(min_length=1, max_length=32)
    direction: Direction
    opened: date = Field(description="Entry date")
    entry_price: float = Field(gt=0)
    quantity: float = Field(gt=0, description="Units bought (long) or sold short")
    stop: float | None = Field(None, gt=0, description="The initial stop, which sets the risk of 1R")
    closed: date | None = Field(None, description="Exit date; null while the trade is open")
    exit_price: float | None = Field(None, gt=0)
    fees: float = Field(0.0, ge=0, description="Commissions and other costs, entry and exit together")
    notes: str = Field("", max_length=10_000)
    run: SuggestingRun | None = Field(None, description="The pinned run that suggested the trade")


class JournalTradeOut(JournalTradeIn):
    id: int
    created_at: str
    updated_at: str
    is_open: bool
    risk: float | None = Field(description="What the initial stop put at risk; null without a stop")
    profit: float | None = Field(description="After fees, in the ticker's currency; null while the trade is open")
    return_pct: float | None = Field(description="Profit after fees as a percent of the position's value at the entry")
    r_multiple: float | None = Field(
        description="Profit after fees in units of the initial risk; null while open or without a stop"
    )


class JournalSummaryOut(BaseModel):
    """Over the closed trades, in R and percent only: tickers in different currencies cannot be summed."""

    open_trades: int
    closed_trades: int
    win_rate_pct: float | None = Field(description="Closed trades with a profit after fees")
    average_return_pct: float | None
    r_trades: int = Field(description="Closed trades with a stop, which have an R multiple")
    average_r: float | None
    total_r: float | None


class JournalOut(BaseModel):
    trades: list[JournalTradeOut] = Field(description="The latest opened first")
    summary: JournalSummaryOut
