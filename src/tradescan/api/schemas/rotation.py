"""Models of POST /api/rotation-backtest."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.backtest import AppliedRuleOut, BacktestConfigOut, MetricsOut, RuleIn, SplitOut
from tradescan.api.schemas.common import Point, SettingsIn, UniverseIn
from tradescan.api.schemas.portfolio import PortfolioTradeOut, TickerContributionOut
from tradescan.backtest.rotation import Rebalance


class RotationSetupIn(UniverseIn):
    """One rotation's setup, shared by a rotation and its sweep. `settings.rotation` sets the holdings and the absolute
    momentum lookback."""

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


class RotationIn(RotationSetupIn):
    engines: list[str] = Field(default_factory=lambda: ["vectorized"], min_length=1)


class RotationConfigOut(BaseModel):
    holdings: int = Field(description="Tickers picked at each rebalance")
    absolute_lookback: int = Field(description="Bars of the absolute momentum check; 0 when it is off")
    rebalance: Rebalance
    safe_asset: str | None = Field(description="Takes the slots of picks that fail the check; null for cash")


class RotationStatsOut(BaseModel):
    rebalances: int
    orders: int = Field(description="Orders filled")
    unfilled_orders: int = Field(description="Dropped because their ticker had no bar before the next rebalance")
    average_holdings: float | None = Field(
        description="Tickers held, the safe asset included, averaged over the closes"
    )
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


class RotationRunOut(BaseModel):
    engine: str
    full: RotationPeriodOut
    in_sample: RotationPeriodOut | None = Field(
        description="The run on the bars before the split; null without a split"
    )
    out_of_sample: RotationPeriodOut | None = Field(
        description="The run from the split on, with fresh equity; null without a split"
    )
    equity: list[Point]
    holdings: list[Point] = Field(description="Tickers held at each close, the safe asset included")
    trades: list[PortfolioTradeOut] = Field(
        description="Holdings: from the buy that opens a position to the sale that empties it, by entry date"
    )
    tickers: list[TickerContributionOut] = Field(
        description="Every ticker with data in watchlist order, the safe asset last"
    )


class RotationOut(BaseModel):
    universe: str
    start: str = Field(description="The first rebalance with a pick: the lookbacks' warm-up is left out")
    end: str
    config: BacktestConfigOut
    rotation: RotationConfigOut
    ranking: AppliedRuleOut
    weighting: AppliedRuleOut
    buy_hold_benchmark: str = Field(description="The benchmark buy & hold compares")
    buy_hold: list[Point] = Field(description="The benchmark scaled to the initial equity, on the run's dates")
    split: SplitOut | None = Field(description="The split of the run's dates; null when it is too short")
    targets: TargetsOut = Field(description="What a rebalance at the last close would hold, the same on every engine")
    runs: list[RotationRunOut] = Field(description="One per engine, in the request's order")
    missing: list[str] = Field(description="Tickers without data")
