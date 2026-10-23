"""Models of POST /api/portfolio-backtest, and the trades and contributions a rotation reports too."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.backtest import (
    AppliedRuleOut,
    BacktestRulesIn,
    BacktestRulesOut,
    MetricsOut,
    RuleIn,
    SplitOut,
    TradeOut,
)
from tradescan.api.schemas.common import Point, SignalParamsIn, UniverseIn


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
        description="Benchmark for buy & hold and for the market filter; omit for the watchlist's, "
        "else the configured benchmark",
    )


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
    skipped_no_room_adds: int = Field(
        description="Closes at which a position's next unit was not ordered for want of room under the exposure cap"
    )


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
    in_sample: PortfolioPeriodOut | None = Field(
        description="The run on the bars before the split; null without a split"
    )
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
