"""Request and response models of the HTTP API.

Floats that are NaN or infinite in pandas are sent as `null`, because JSON cannot represent them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from tradescan.signals.base import Direction, Family

# ---------------------------------------------------------------------------
# Requests


class UniverseIn(BaseModel):
    watchlist: str | None = Field(None, description="Watchlist name, e.g. us_large")
    tickers: list[str] | None = Field(None, description="Ad-hoc tickers instead of a watchlist")

    @model_validator(mode="after")
    def _one_source(self) -> UniverseIn:
        if bool(self.watchlist) == bool(self.tickers):
            raise ValueError("Give either a watchlist or a list of tickers")
        return self


class SignalFilterIn(BaseModel):
    signals: list[str] = Field(default_factory=list, description="Signal names; empty means all")
    families: list[Family] = Field(default_factory=list)
    direction: Direction | None = Field(None, description="Omit for both directions")


class AccountIn(BaseModel):
    equity: float | None = Field(None, gt=0)
    risk_pct: float | None = Field(None, gt=0, le=100)
    lot_size: float | None = Field(None, gt=0)


class ScanIn(UniverseIn, SignalFilterIn):
    account: AccountIn = Field(default_factory=AccountIn)
    fresh_bars: int | None = Field(None, ge=1, le=60)
    min_score: float | None = None
    benchmark: str | None = None
    period: str | None = None


class MarketIn(UniverseIn):
    benchmark: str | None = None
    period: str | None = None


class EdgeIn(UniverseIn, SignalFilterIn):
    horizons: list[int] = Field(default_factory=lambda: [5, 10, 20], min_length=1)
    min_events: int = Field(0, ge=0)
    period: str | None = None


class BacktestIn(BaseModel):
    ticker: str = Field(min_length=1)
    signal: str
    engines: list[str] = Field(default_factory=lambda: ["vectorized"], min_length=1)
    account: AccountIn = Field(default_factory=AccountIn)
    atr_mult: float | None = Field(None, gt=0)
    target_r: float | None = Field(None, gt=0)
    max_hold_bars: int | None = Field(None, ge=1)
    commission_pct: float | None = Field(None, ge=0)
    slippage_pct: float | None = Field(None, ge=0)
    period: str | None = None


# ---------------------------------------------------------------------------
# Shared responses


class Point(BaseModel):
    time: str
    value: float


class SignalOut(BaseModel):
    name: str
    family: Family
    direction: Direction
    weight: float
    description: str


class WatchlistOut(BaseModel):
    name: str
    tickers: list[str]
    benchmark: str | None


class AccountDefaults(BaseModel):
    equity: float
    risk_pct: float
    max_position_pct: float
    lot_size: float


class ScanDefaults(BaseModel):
    fresh_bars: int
    min_score: float
    edge_horizon: int
    benchmark: str
    period: str


class BacktestDefaults(BaseModel):
    period: str
    atr_mult: float
    target_r: float
    max_hold_bars: int
    commission_pct: float
    slippage_pct: float


class ConfigOut(BaseModel):
    version: str
    account: AccountDefaults
    scan: ScanDefaults
    backtest: BacktestDefaults
    targets_r: list[float]
    families: list[Family]
    engines: list[str]


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


class EdgeStatsOut(BaseModel):
    signal: str
    horizon: int
    events: int
    win_rate: float | None
    mean_return: float | None
    median_return: float | None
    baseline_return: float | None
    edge: float | None


# ---------------------------------------------------------------------------
# Scan and market


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


class MarketOut(BaseModel):
    universe: str
    regime: RegimeOut
    missing: list[str]


# ---------------------------------------------------------------------------
# Edge


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


# ---------------------------------------------------------------------------
# Backtest


class MetricsOut(BaseModel):
    total_return_pct: float | None
    cagr_pct: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown_pct: float | None
    trades: int
    win_rate_pct: float | None
    profit_factor: float | None
    profit_factor_infinite: bool = Field(description="True when there were winners and no losers")
    expectancy_r: float | None
    sqn: float | None
    exposure_pct: float | None
    buy_hold_pct: float | None


class TradeOut(BaseModel):
    direction: Direction
    signal_date: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    r_multiple: float | None
    exit_reason: str


class EngineRunOut(BaseModel):
    engine: str
    metrics: MetricsOut
    equity: list[Point]
    trades: list[TradeOut]


class BacktestConfigOut(BaseModel):
    initial_equity: float
    risk_pct: float
    max_position_pct: float
    lot_size: float
    atr_period: int
    atr_mult: float
    target_r: float
    max_hold_bars: int
    commission_pct: float
    slippage_pct: float


class BacktestOut(BaseModel):
    ticker: str
    signal: str
    direction: Direction
    start: str
    end: str
    config: BacktestConfigOut
    buy_hold: list[Point]
    runs: list[EngineRunOut]


# ---------------------------------------------------------------------------
# Chart


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


class ErrorOut(BaseModel):
    detail: str
