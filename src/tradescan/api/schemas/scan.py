"""Models of POST /api/scan."""

from __future__ import annotations

from pydantic import BaseModel

from tradescan.api.schemas.common import (
    SETTINGS_FIELD,
    SIGNAL_PARAMS_FIELD,
    SettingsIn,
    SignalFilterIn,
    SignalParamsIn,
    UniverseIn,
)
from tradescan.api.schemas.edge import EdgeStatsOut
from tradescan.api.schemas.market import RegimeOut
from tradescan.signals.base import Direction, Family


class ScanIn(UniverseIn, SignalFilterIn):
    settings: SettingsIn = SETTINGS_FIELD
    signal_params: dict[str, SignalParamsIn] = SIGNAL_PARAMS_FIELD
    benchmark: str | None = None
    period: str | None = None


class FiredSignalOut(BaseModel):
    name: str
    family: Family
    bars_ago: int
    weight: float


class ScoreOut(BaseModel):
    total: float
    signals: float
    trend: float
    weekly: float
    relative_strength: float


class RiskOut(BaseModel):
    entry: float
    stop: float | None
    targets: list[float | None]
    risk_per_share: float | None
    size: float
    position_value: float | None
    risk_amount: float | None


class HitOut(BaseModel):
    ticker: str
    direction: Direction
    date: str
    close: float
    change_pct: float | None
    atr: float | None
    atr_pct: float | None
    adx: float | None
    daily_trend: str
    weekly_trend: str
    rs_percentile: float | None
    fired: list[FiredSignalOut]
    score: ScoreOut
    risk: RiskOut
    edge: EdgeStatsOut | None


class ScanOut(BaseModel):
    universe: str
    regime: RegimeOut
    hits: list[HitOut]
    missing: list[str]
    skipped: list[str]
    min_score: float
    fresh_bars: int
    edge_horizon: int
