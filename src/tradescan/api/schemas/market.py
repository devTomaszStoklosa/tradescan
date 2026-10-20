"""Models of POST /api/market, and the market regime a scan reports too."""

from __future__ import annotations

from pydantic import BaseModel

from tradescan.api.schemas.common import SETTINGS_FIELD, SettingsIn, UniverseIn


class MarketIn(UniverseIn):
    settings: SettingsIn = SETTINGS_FIELD
    benchmark: str | None = None
    period: str | None = None


class RegimeOut(BaseModel):
    benchmark: str
    benchmark_close: float | None
    benchmark_above_slow: bool | None
    benchmark_fast_above_slow: bool | None
    pct_above_fast: float | None
    pct_above_slow: float | None
    new_highs: int
    new_lows: int
    universe_size: int
    regime: str


class MarketOut(BaseModel):
    universe: str
    regime: RegimeOut
    missing: list[str]
