"""Request and response models of the HTTP API.

Floats that are NaN or infinite in pandas are sent as `null`, because JSON cannot represent them.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradescan.backtest.rotation import Rebalance
from tradescan.backtest.sweep import MAX_VALUES, MIN_VALUES, SweepTarget
from tradescan.backtest.tickers import Period
from tradescan.backtest.walk_forward import DEFAULT_SELECTION_METRIC, WindowScheme
from tradescan.params import ParamKind
from tradescan.signals.base import Direction, Family
from tradescan.storage.runs import MAX_PINNED_RUNS

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


class BacktestRulesIn(_Request):
    """What a backtest tests apart from the ticker, shared by a backtest, a sweep and a watchlist backtest."""

    signal: str
    params: SignalParamsIn = Field(default_factory=dict, description="The signal's parameters, e.g. {\"period\": 30}")
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


class SweepAxisIn(_Request):
    target: SweepTarget = Field(
        description="What holds the parameter: the signal, the entry rule, an exit rule, an entry filter or a settings section"
    )
    owner: str | None = Field(
        None, description="The exit rule, entry filter or settings section; omit for the signal and the entry rule"
    )
    name: str = Field(description="The parameter, e.g. oversold")
    values: list[float] = Field(min_length=MIN_VALUES, max_length=MAX_VALUES, description="The values to try, in order")


class SweepIn(BacktestSetupIn):
    axes: list[SweepAxisIn] = Field(min_length=1, description="One or two parameters; the first changes slowest")


class WalkForwardIn(SweepIn):
    """`settings.walk_forward` sets the windows, the in-sample length and the trades a pick needs;
    `settings.backtest.oos_pct` has no effect, since the windows split the history."""

    scheme: WindowScheme = Field(
        WindowScheme.ROLLING,
        description="rolling: in-sample windows of fixed length that slide along; anchored: in-sample windows from the first bar",
    )
    metric: str = Field(
        DEFAULT_SELECTION_METRIC,
        description="Each in-sample window picks the combination with the highest value of this metric; /api/config lists them",
    )


class WatchlistBacktestIn(UniverseIn, BacktestRulesIn):
    benchmark: str | None = Field(
        None, description="Benchmark the market filter compares; omit for the watchlist's, else the configured benchmark"
    )


class PortfolioIn(UniverseIn, BacktestRulesIn):
    """`settings.portfolio` sets the max positions and the max exposure."""

    engines: list[str] = Field(default_factory=lambda: ["vectorized"], min_length=1)
    priority: RuleIn | None = Field(
        None, description="Which signals go first when more fire than there is room for; omit for the default priority"
    )
    score_signal_params: dict[str, SignalParamsIn] = Field(
        default_factory=dict,
        description="Parameters of the signals the score priority counts besides the traded one, by signal name, "
        'e.g. {"donchian_breakout": {"period": 55}}; the traded signal\'s come from params',
    )
    benchmark: str | None = Field(
        None,
        description="Benchmark for buy & hold and for the market filter; omit for the watchlist's, else the configured benchmark",
    )


class RotationIn(UniverseIn):
    """`settings.rotation` sets the holdings and the absolute momentum lookback."""

    ranking: RuleIn | None = Field(None, description="How the tickers are ranked; omit for the default ranking")
    weighting: RuleIn | None = Field(None, description="How the picks share the equity; omit for the default weighting")
    rebalance: Rebalance = Field(Rebalance.MONTHLY, description="Rebalance at the last close of every week or month")
    safe_asset: str | None = Field(
        None, description="Takes the slots of picks whose absolute momentum is at or below 0; omit for cash"
    )
    settings: SettingsIn = Field(
        default_factory=dict,
        description='Per-run overrides by settings section, e.g. {"rotation": {"holdings": 3}}; '
        "backtest.oos_pct sets the out-of-sample share",
    )
    benchmark: str | None = Field(
        None, description="Benchmark for buy & hold; omit for the watchlist's, else the configured benchmark"
    )
    period: str | None = None


class ChartIn(_Request):
    ticker: str = Field(min_length=1)
    signals: list[str] = Field(default_factory=list, description="Signals whose events to mark")
    signal_params: dict[str, SignalParamsIn] = _SIGNAL_PARAMS
    period: str | None = None


class PinnedRunIn(_Request):
    id: str = Field(min_length=1, max_length=100)
    slot: int = Field(ge=1, le=MAX_PINNED_RUNS, description="The run's number and colour in Compare")
    name: str = Field(max_length=200)
    hidden: bool = Field(description="True when Compare leaves the run out of its tables and chart")
    pinned_at: str = Field(max_length=40, description="When the run was pinned, as an ISO 8601 time")
    format: int = Field(ge=1, description="The UI's runs-file version the snapshot was written in")
    snapshot: dict[str, Any] = Field(description="The run as the UI keeps it; the server stores it unchanged")


class PinnedRunPatchIn(_Request):
    name: str | None = Field(None, max_length=200)
    hidden: bool | None = None


class SuggestingRun(_Request):
    """A copy of the pinned run that suggested a trade, so the trade keeps it after the run is unpinned."""

    format: int = Field(ge=1, description="The UI's runs-file version the snapshot was written in")
    snapshot: dict[str, Any] = Field(description="The run as the UI keeps it, its pin name included")


class JournalTradeIn(_Request):
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


class FilterRuleOut(RuleOut):
    needs_benchmark: bool = Field(description="True when the filter compares the benchmark, which a backtest then loads")


class PriorityRuleOut(RuleOut):
    needs_scan: bool = Field(
        description="True when the rule reads the scanner's settings (scoring, trend, scan.fresh_bars), which a run can override"
    )


class WatchlistOut(BaseModel):
    name: str
    tickers: list[str]
    benchmark: str | None


class SweepLimitsOut(BaseModel):
    max_axes: int
    min_values: int
    max_values: int
    max_combinations: int
    sections: list[str] = Field(description="Settings sections whose parameters a sweep can change")
    fixed: list[str] = Field(description="section.name of settings a sweep cannot change")
    min_period_bars: int = Field(description="Bars each period needs for an in-sample/out-of-sample split")


class WalkForwardLimitsOut(BaseModel):
    max_runs: int = Field(description="Combinations times in-sample windows (the next one included) a walk-forward runs at most")
    schemes: list[WindowScheme]
    default_scheme: WindowScheme
    metrics: list[str] = Field(description="Metrics an in-sample window can pick by, the highest first")
    default_metric: str
    fixed: list[str] = Field(description="section.name of settings a walk-forward cannot sweep")


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
    filter_rules: list[FilterRuleOut] = Field(description="Entry filters; a backtest uses none unless it names them")
    default_entry: str
    default_exits: list[str]
    priority_rules: list[PriorityRuleOut] = Field(description="Priority rules of a portfolio backtest")
    default_priority: str
    ranking_rules: list[RuleOut] = Field(description="How a rotation ranks the tickers: the priority rules that read bars only")
    default_ranking: str
    weight_rules: list[RuleOut] = Field(description="How a rotation's picks share the equity")
    default_weighting: str
    rebalances: list[Rebalance] = Field(description="How often a rotation rebalances")
    sweep: SweepLimitsOut
    walk_forward: WalkForwardLimitsOut


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
    out_of_sample: MetricsOut | None = Field(description="The run from the split on, with fresh equity; null without a split")
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


class SweepAxisOut(BaseModel):
    target: SweepTarget
    owner: str | None
    name: str
    key: str = Field(description="target[.owner].name")
    label: str
    unit: str
    kind: ParamKind
    current: float = Field(description="The value in the setup the sweep started from")
    values: list[float]


class SweepCellOut(BaseModel):
    values: list[float] = Field(description="One value per axis, in axis order")
    in_sample: MetricsOut | None
    out_of_sample: MetricsOut | None
    error: str | None = Field(description="Why this combination could not run, e.g. a rule between two parameters")


class SweepOut(BacktestSetupOut):
    engine: str = Field(description="Sweeps run on this engine")
    split: SplitOut
    axes: list[SweepAxisOut]
    cells: list[SweepCellOut] = Field(description="Every combination; the first axis changes slowest")


# ---------------------------------------------------------------------------
# Walk-forward


class WalkForwardSettingsOut(BaseModel):
    windows: int
    in_sample_ratio: float
    min_trades: int
    in_sample_bars: int = Field(description="Bars of each in-sample window; with the anchored scheme of the first one")
    out_of_sample_bars: int = Field(description="Bars of each out-of-sample window")


class CombinationErrorOut(BaseModel):
    values: list[float] = Field(description="One value per axis, in axis order")
    error: str = Field(description="Why this combination could not run, e.g. a rule between two parameters")


class WindowPickOut(BaseModel):
    in_sample_start: str
    in_sample_end: str
    values: list[float] | None = Field(description="The picked combination, one value per axis; null when none qualified")
    qualified: int = Field(description="Combinations with a value and enough in-sample trades to be picked")
    in_sample: MetricsOut | None = Field(description="The pick's metrics on the in-sample window")


class WalkForwardWindowOut(WindowPickOut):
    out_of_sample_start: str
    out_of_sample_end: str
    traded_from: str | None = Field(
        description="First bar of the window's own part of the stitched curve: later than out_of_sample_start while a "
        "position of the window before was still open; null when the window had no part of its own"
    )
    traded_to: str | None = Field(
        description="The bar where the next window took over: the next window's first bar, or later while a position of "
        "this window was still open; the last bar for the last window; null when the window had no part of its own"
    )
    out_of_sample: MetricsOut | None = Field(description="Of the window's own part of the stitched curve; null without one")


class WalkForwardOut(BacktestSetupOut):
    engine: str = Field(description="Walk-forwards run on this engine")
    scheme: WindowScheme
    metric: str = Field(description="The metric each in-sample window picked by")
    walk_forward: WalkForwardSettingsOut
    axes: list[SweepAxisOut]
    combinations: int = Field(description="Combinations of the axes' values, including those that could not run")
    errors: list[CombinationErrorOut] = Field(description="The combinations that could not run")
    out_of_sample_start: str = Field(description="The first bar of the stitched curve")
    windows: list[WalkForwardWindowOut]
    next: WindowPickOut = Field(
        description="The pick of the in-sample window that ends on the last bar: the setting to trade next"
    )
    metrics: MetricsOut = Field(description="Of the stitched out-of-sample curve")
    unchanged: MetricsOut = Field(description="The setup as given, traded over the same bars")
    efficiency: float | None = Field(
        description="Stitched out-of-sample CAGR over the average in-sample CAGR of the picks; "
        "null when that average is not above 0"
    )
    equity: list[Point] = Field(description="The stitched out-of-sample curve")
    unchanged_equity: list[Point]
    buy_hold: list[Point] = Field(description="Buy & hold from the first out-of-sample bar, scaled to the initial equity")
    trades: list[TradeOut] = Field(description="Every out-of-sample trade, window after window")


# ---------------------------------------------------------------------------
# Watchlist backtest


class TickerRunOut(BaseModel):
    ticker: str
    start: str
    end: str
    split: SplitOut | None = Field(description="This ticker's in-sample/out-of-sample split; null when its history is too short")
    metrics: MetricsOut = Field(description="The full history")
    in_sample: MetricsOut | None
    out_of_sample: MetricsOut | None


class PooledTradesOut(BaseModel):
    trades: int
    win_rate_pct: float | None
    expectancy_r: float | None
    profit_factor_r: float | None = Field(description="Gross R won / gross R lost")
    profit_factor_infinite: bool = Field(description="True when there were winners and no losers")
    sqn: float | None


class MetricSpreadOut(BaseModel):
    metric: str
    tickers: int = Field(description="Tickers with a value; a trade metric has none for a ticker without trades")
    median: float | None = Field(
        description="This and the other values are null when no ticker has a value, or when they are infinite "
        "(a profit factor without losers)"
    )
    p25: float | None
    p75: float | None
    minimum: float | None
    maximum: float | None
    above_break_even_pct: float | None = Field(description="Share of the tickers above break-even; null for metrics without one")


class PeriodSummaryOut(BaseModel):
    period: Period
    tickers: int = Field(description="Tickers that have this period")
    pooled: PooledTradesOut = Field(description="Every ticker's closed trades taken together")
    spread: list[MetricSpreadOut] = Field(description="How each metric is spread across the tickers")


class WatchlistBacktestOut(BacktestRulesOut):
    universe: str
    engine: str = Field(description="Every ticker runs on this engine")
    rows: list[TickerRunOut] = Field(description="One per ticker with data, in watchlist order")
    periods: list[PeriodSummaryOut] = Field(description="The full history, in-sample and out-of-sample")
    missing: list[str] = Field(description="Tickers without data")


# ---------------------------------------------------------------------------
# Portfolio backtest


class PortfolioConfigOut(BaseModel):
    max_positions: int = Field(description="Open positions plus entry orders waiting to fill")
    max_exposure_pct: float = Field(description="Gross value of the open positions and waiting orders, % of equity")


class PortfolioStatsOut(BaseModel):
    average_positions: float | None
    max_positions: int
    average_exposure_pct: float | None = Field(description="Gross value of the open positions, % of equity, averaged")
    max_exposure_pct: float | None
    orders: int = Field(description="Entry orders placed")
    skipped_no_slot: int = Field(description="Signals skipped because every slot was taken")
    skipped_no_room: int = Field(description="Signals skipped because less than one lot fitted under the exposure cap")


class PortfolioPeriodOut(BaseModel):
    metrics: MetricsOut = Field(
        description="buy_hold_pct is the benchmark's; exposure_pct is the share of closes with an open position"
    )
    stats: PortfolioStatsOut


class PortfolioTradeOut(TradeOut):
    ticker: str


class TickerContributionOut(BaseModel):
    ticker: str
    trades: int = Field(description="Closed trades")
    pnl: float = Field(description="Net, with a trade still open marked to its last close")
    contribution_pct: float | None = Field(description="pnl as a percent of the initial equity")
    win_rate_pct: float | None
    expectancy_r: float | None


class PortfolioRunOut(BaseModel):
    engine: str
    full: PortfolioPeriodOut
    in_sample: PortfolioPeriodOut | None = Field(description="The run on the bars before the split; null without a split")
    out_of_sample: PortfolioPeriodOut | None = Field(
        description="The run from the split on, with fresh equity; null without a split"
    )
    equity: list[Point]
    positions: list[Point] = Field(description="Open positions at each close")
    trades: list[PortfolioTradeOut] = Field(description="By entry date, then watchlist order")
    tickers: list[TickerContributionOut] = Field(description="Every ticker with data, in watchlist order")


class ScanInputsOut(BaseModel):
    settings: dict[str, dict[str, int | float | list[float] | dict[str, float]]] = Field(
        description="The scanner's settings the score read, by section as a request's settings name them: "
        "every scoring and trend parameter and scan.fresh_bars"
    )
    signal_params: dict[str, dict[str, float | list[float]]] = Field(
        description="Parameters of the signals the score counted besides the traded one, by signal name"
    )


class PortfolioOut(BacktestRulesOut):
    universe: str
    start: str
    end: str
    portfolio: PortfolioConfigOut
    priority: AppliedRuleOut
    scan: ScanInputsOut | None = Field(
        description="What the priority read of the scanner besides the bars; null when it does not read the scanner"
    )
    buy_hold_benchmark: str = Field(description="The benchmark buy & hold compares")
    buy_hold: list[Point] = Field(description="The benchmark scaled to the initial equity")
    split: SplitOut | None = Field(description="The split of the shared calendar; null when it is too short")
    runs: list[PortfolioRunOut]
    missing: list[str] = Field(description="Tickers without data")


# ---------------------------------------------------------------------------
# Momentum rotation


class RotationConfigOut(BaseModel):
    holdings: int = Field(description="Tickers picked at each rebalance")
    absolute_lookback: int = Field(description="Bars of the absolute momentum check; 0 when it is off")
    rebalance: Rebalance
    safe_asset: str | None = Field(description="Takes the slots of picks that fail the check; null for cash")


class RotationStatsOut(BaseModel):
    rebalances: int
    orders: int = Field(description="Orders filled")
    unfilled_orders: int = Field(description="Dropped because their ticker had no bar before the next rebalance")
    average_holdings: float | None = Field(description="Tickers held, the safe asset included, averaged over the closes")
    max_holdings: int
    average_exposure_pct: float | None = Field(description="Gross value of the holdings, % of equity, averaged")
    average_safe_pct: float | None = Field(description="Value of the safe asset, % of equity, averaged")
    average_cash_pct: float | None
    turnover_pct: float | None = Field(description="Half the value traded per year, % of the average equity")
    commissions: float


class RotationPeriodOut(BaseModel):
    metrics: MetricsOut = Field(
        description="buy_hold_pct is the benchmark's; exposure_pct is the share of closes with a holding; "
        "without a stop, expectancy_r and sqn are null"
    )
    stats: RotationStatsOut


class PickOut(BaseModel):
    ticker: str
    score: float | None = Field(description="The ranking's score")
    momentum_pct: float | None = Field(description="Return over the absolute momentum lookback, %; null when it is off")
    weight_pct: float = Field(description="The pick's share of equity")
    held: bool = Field(description="False when its absolute momentum hands its slot to the safe asset or cash")


class TargetsOut(BaseModel):
    date: str
    picks: list[PickOut] = Field(description="By rank")
    safe_pct: float = Field(description="Share of equity in the safe asset for the picks that failed the check")
    cash_pct: float


class RotationOut(BaseModel):
    universe: str
    engine: str
    start: str = Field(description="The first rebalance with a pick: the lookbacks' warm-up is left out")
    end: str
    config: BacktestConfigOut
    rotation: RotationConfigOut
    ranking: AppliedRuleOut
    weighting: AppliedRuleOut
    buy_hold_benchmark: str = Field(description="The benchmark buy & hold compares")
    buy_hold: list[Point] = Field(description="The benchmark scaled to the initial equity, on the run's dates")
    split: SplitOut | None = Field(description="The split of the run's dates; null when it is too short")
    full: RotationPeriodOut
    in_sample: RotationPeriodOut | None = Field(description="The run on the bars before the split; null without a split")
    out_of_sample: RotationPeriodOut | None = Field(
        description="The run from the split on, with fresh equity; null without a split"
    )
    equity: list[Point]
    holdings: list[Point] = Field(description="Tickers held at each close, the safe asset included")
    targets: TargetsOut = Field(description="What a rebalance at the last close would hold")
    trades: list[PortfolioTradeOut] = Field(
        description="Holdings: from the buy that opens a position to the sale that empties it, by entry date"
    )
    tickers: list[TickerContributionOut] = Field(description="Every ticker with data in watchlist order, the safe asset last")
    missing: list[str] = Field(description="Tickers without data")


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


# ---------------------------------------------------------------------------
# Pinned runs and the trade journal


class PinnedRunOut(PinnedRunIn):
    """A pinned run as the server stores it."""


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


class ErrorOut(BaseModel):
    detail: str
