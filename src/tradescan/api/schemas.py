"""Request and response models of the HTTP API.

Floats that are NaN or infinite in pandas are sent as `null`, because JSON cannot represent them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradescan.params import ParamKind
from tradescan.signals.base import Direction, Family

# ---------------------------------------------------------------------------
# Requests

ParamValueIn = float | list[float] | dict[str, float]
SettingsIn = dict[str, dict[str, ParamValueIn]]
SignalParamsIn = dict[str, float | list[float]]

_SETTINGS = Field(
    default_factory=dict,
    description='Per-run overrides by settings section, e.g. {"risk": {"atr_mult": 3}}; see /api/config for every parameter',
)
_SIGNAL_PARAMS = Field(
    default_factory=dict,
    description='Per-run signal parameters by signal name, e.g. {"connors_rsi2_long": {"oversold": 15}}',
)


class _Request(BaseModel):
    """Unknown fields are an error, so a misspelt or removed field never passes silently."""

    model_config = ConfigDict(extra="forbid")


class UniverseIn(_Request):
    watchlist: str | None = Field(None, description="Watchlist name, e.g. us_large")
    tickers: list[str] | None = Field(None, description="Ad-hoc tickers instead of a watchlist")

    @model_validator(mode="after")
    def _one_source(self) -> UniverseIn:
        if bool(self.watchlist) == bool(self.tickers):
            raise ValueError("Give either a watchlist or a list of tickers")
        return self


class SignalFilterIn(_Request):
    signals: list[str] = Field(default_factory=list, description="Signal names; empty means all")
    families: list[Family] = Field(default_factory=list)
    direction: Direction | None = Field(None, description="Omit for both directions")


class ScanIn(UniverseIn, SignalFilterIn):
    settings: SettingsIn = _SETTINGS
    signal_params: dict[str, SignalParamsIn] = _SIGNAL_PARAMS
    benchmark: str | None = None
    period: str | None = None


class MarketIn(UniverseIn):
    settings: SettingsIn = _SETTINGS
    benchmark: str | None = None
    period: str | None = None


class EdgeIn(UniverseIn, SignalFilterIn):
    signal_params: dict[str, SignalParamsIn] = _SIGNAL_PARAMS
    horizons: list[int] = Field(default_factory=lambda: [5, 10, 20], min_length=1)
    min_events: int = Field(0, ge=0)
    period: str | None = None


class RuleIn(_Request):
    name: str = Field(description="Rule name; /api/config lists the entry and exit rules")
    params: SignalParamsIn = Field(default_factory=dict, description="The rule's parameters, e.g. {\"target_r\": 3}")


class BacktestIn(_Request):
    ticker: str = Field(min_length=1)
    signal: str
    engines: list[str] = Field(default_factory=lambda: ["vectorized"], min_length=1)
    params: SignalParamsIn = Field(default_factory=dict, description="The signal's parameters, e.g. {\"period\": 30}")
    settings: SettingsIn = _SETTINGS
    entry: RuleIn | None = Field(None, description="Entry rule; omit for the default entry")
    exits: list[RuleIn] | None = Field(
        None, description="Exit rules on top of the initial stop; omit for the default exits, [] for the stop only"
    )
    period: str | None = None


class ChartIn(_Request):
    ticker: str = Field(min_length=1)
    signals: list[str] = Field(default_factory=list, description="Signals whose events to mark")
    signal_params: dict[str, SignalParamsIn] = _SIGNAL_PARAMS
    period: str | None = None


# ---------------------------------------------------------------------------
# Shared responses


class Point(BaseModel):
    time: str
    value: float


class ParamSpecOut(BaseModel):
    name: str
    kind: ParamKind
    label: str
    unit: str
    help: str
    default: int | float | list[float] | dict[str, float]
    minimum: float
    maximum: float
    step: float
    keys: list[str] | None = Field(None, description="Allowed keys of a weights parameter; null means any")


class SettingsSectionOut(BaseModel):
    name: str
    label: str
    params: list[ParamSpecOut]


class SignalOut(BaseModel):
    name: str
    family: Family
    direction: Direction
    weight: float
    description: str = Field(description="The rule with the default parameters filled in")
    template: str = Field(description='The rule with {parameter} placeholders; format specs "", "g" and ".0%"')
    params: list[ParamSpecOut]


class RuleOut(BaseModel):
    name: str
    label: str
    description: str = Field(description="The rule with the default parameters filled in")
    template: str = Field(description='The rule with {parameter} placeholders; format specs "", "g" and ".0%"')
    params: list[ParamSpecOut]


class WatchlistOut(BaseModel):
    name: str
    tickers: list[str]
    benchmark: str | None


class ConfigOut(BaseModel):
    version: str
    scan_period: str
    backtest_period: str
    benchmark: str
    sections: list[SettingsSectionOut] = Field(description="Adjustable settings; defaults come from settings.toml")
    families: list[Family]
    engines: list[str]
    entry_rules: list[RuleOut]
    exit_rules: list[RuleOut]
    default_entry: str
    default_exits: list[str]


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
    commission_pct: float
    slippage_pct: float
    bars_per_year: int


class AppliedRuleOut(BaseModel):
    name: str
    label: str
    description: str = Field(description="The rule with this run's parameters")
    params: dict[str, float | list[float]] = Field(description="The rule's parameters used in this run")


class BacktestOut(BaseModel):
    ticker: str
    signal: str
    direction: Direction
    description: str = Field(description="The signal's rule with this run's parameters")
    params: dict[str, float | list[float]] = Field(description="The signal's parameters used in this run")
    start: str
    end: str
    config: BacktestConfigOut
    entry: AppliedRuleOut
    exits: list[AppliedRuleOut] = Field(description="Exit rules on top of the initial stop, in the order given")
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
