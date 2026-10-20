"""Models of POST /api/chart."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.common import SIGNAL_PARAMS_FIELD, Point, RequestModel, SignalParamsIn
from tradescan.signals.base import Direction


class ChartIn(RequestModel):
    ticker: str = Field(min_length=1)
    signals: list[str] = Field(default_factory=list, description="Signals whose events to mark")
    signal_params: dict[str, SignalParamsIn] = SIGNAL_PARAMS_FIELD
    period: str | None = None


class Candle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartEventOut(BaseModel):
    time: str
    signal: str
    direction: Direction


class ChartOut(BaseModel):
    ticker: str
    candles: list[Candle]
    sma_fast: list[Point]
    sma_slow: list[Point]
    events: list[ChartEventOut]
