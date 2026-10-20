"""Models of POST /api/edge, and the edge statistics a scan reports per hit too."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.common import SIGNAL_PARAMS_FIELD, SignalFilterIn, SignalParamsIn, UniverseIn
from tradescan.signals.base import Direction, Family


class EdgeIn(UniverseIn, SignalFilterIn):
    signal_params: dict[str, SignalParamsIn] = SIGNAL_PARAMS_FIELD
    horizons: list[int] = Field(default_factory=lambda: [5, 10, 20], min_length=1)
    min_events: int = Field(0, ge=0)
    period: str | None = None


class EdgeStatsOut(BaseModel):
    signal: str
    horizon: int
    events: int
    win_rate: float | None
    mean_return: float | None
    median_return: float | None
    baseline_return: float | None
    edge: float | None


class EdgeRowOut(BaseModel):
    signal: str
    family: Family
    direction: Direction
    description: str
    stats: list[EdgeStatsOut]


class EdgeOut(BaseModel):
    universe: str
    horizons: list[int]
    tickers: int
    rows: list[EdgeRowOut]
    missing: list[str]
