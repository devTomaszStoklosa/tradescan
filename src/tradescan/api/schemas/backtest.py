"""Models of POST /api/backtest, and the setup, metrics and trades the other backtests share."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.common import Point, RequestModel, SettingsIn, SignalParamsIn
from tradescan.signals.base import Direction


class RuleIn(RequestModel):
    name: str = Field(description="Rule name; /api/config lists the entry and exit rules")
    params: SignalParamsIn = Field(default_factory=dict, description='The rule\'s parameters, e.g. {"target_r": 3}')


class BacktestRulesIn(RequestModel):
    """What a backtest tests apart from the ticker, shared by a backtest, a sweep and a watchlist backtest."""

    signal: str
    params: SignalParamsIn = Field(default_factory=dict, description='The signal\'s parameters, e.g. {"period": 30}')
    settings: SettingsIn = Field(
        default_factory=dict,
        description='Per-run overrides by settings section, e.g. {"risk": {"atr_mult": 3}}; '
        "backtest.oos_pct sets the out-of-sample share",
    )
    entry: RuleIn | None = Field(None, description="Entry rule; omit for the default entry")
    exits: list[RuleIn] | None = Field(
        None, description="Exit rules on top of the initial stop; omit for the default exits, [] for the stop only"
    )
    filters: list[RuleIn] = Field(
        default_factory=list, description="Entry filters; a signal trades only when every one allows it"
    )
    benchmark: str | None = Field(
        None, description="Benchmark the market filter compares; omit for the configured benchmark"
    )
    period: str | None = None


class BacktestSetupIn(BacktestRulesIn):
    """One backtest's setup, shared by a backtest and a sweep."""

    ticker: str = Field(min_length=1)


class BacktestIn(BacktestSetupIn):
    engines: list[str] = Field(default_factory=lambda: ["vectorized"], min_length=1)


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


class FillOut(BaseModel):
    date: str
    price: float


class TradeOut(BaseModel):
    direction: Direction
    signal_date: str
    entry_date: str = Field(description="The first unit's fill")
    exit_date: str
    entry_price: float = Field(description="The average fill of the units")
    exit_price: float
    size: float = Field(description="Of all units")
    pnl: float
    r_multiple: float | None = Field(description="P&L as a multiple of one unit's risk at its initial stop")
    exit_reason: str
    adds: list[FillOut] = Field(description="The units added after the first by pyramiding, in order")


class PercentilesOut(BaseModel):
    p5: float | None
    p25: float | None
    p50: float | None = Field(description="The median")
    p75: float | None
    p95: float | None


class MonteCarloPathOut(BaseModel):
    final_return_pct: float | None
    max_drawdown_pct: float | None = Field(description="Negative, like the run's max drawdown")
    longest_losing_streak: int = Field(description="Consecutive losing trades")


class MonteCarloMethodOut(BaseModel):
    name: str
    label: str
    description: str
    final_return_pct: PercentilesOut
    max_drawdown_pct: PercentilesOut = Field(description="Negative: the 5th percentile is the deepest drawdown but 5%")
    longest_losing_streak: PercentilesOut
    ruin_pct: float = Field(description="Share of the simulations whose drawdown reached the ruin level")


class MonteCarloOut(BaseModel):
    simulations: int = Field(description="Simulations per method")
    ruin_drawdown_pct: float = Field(description="A drawdown from the peak at least this deep counts as ruin")
    seed: int
    risk_pct: float = Field(description="Each trade changes equity by this percent times its R multiple")
    trades: int = Field(description="Closed trades resampled; every simulated sequence has as many")
    actual: MonteCarloPathOut = Field(description="The run's own order of trades under the same model")
    methods: list[MonteCarloMethodOut]


class EngineRunOut(BaseModel):
    engine: str
    metrics: MetricsOut
    in_sample: MetricsOut | None = Field(description="The run on the history before the split; null without a split")
    out_of_sample: MetricsOut | None = Field(
        description="The run from the split on, with fresh equity; null without a split"
    )
    monte_carlo: MonteCarloOut | None = Field(
        description="The full history's closed trades resampled in R; null with fewer than two closed trades"
    )
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
    oos_pct: float
    max_units: int = Field(description="The first entry plus the adds; 1 is no pyramiding")
    add_every_atr: float = Field(description="Distance between the units, in ATRs of the signal bar")


class AppliedRuleOut(BaseModel):
    name: str
    label: str
    description: str = Field(description="The rule with this run's parameters")
    params: dict[str, float | list[float]] = Field(description="The rule's parameters used in this run")


class SplitOut(BaseModel):
    oos_pct: float
    in_sample_start: str
    in_sample_end: str
    out_of_sample_start: str
    out_of_sample_end: str


class BacktestRulesOut(BaseModel):
    signal: str
    direction: Direction
    description: str = Field(description="The signal's rule with this run's parameters")
    params: dict[str, float | list[float]] = Field(description="The signal's parameters used in this run")
    config: BacktestConfigOut
    entry: AppliedRuleOut
    exits: list[AppliedRuleOut] = Field(description="Exit rules on top of the initial stop, in the order given")
    filters: list[AppliedRuleOut] = Field(description="Entry filters, in the order given")
    benchmark: str | None = Field(description="The benchmark the filters compared; null when no filter reads one")


class BacktestSetupOut(BacktestRulesOut):
    ticker: str
    start: str
    end: str


class BacktestOut(BacktestSetupOut):
    split: SplitOut | None = Field(description="The in-sample/out-of-sample split; null when the history is too short")
    buy_hold: list[Point]
    runs: list[EngineRunOut]
