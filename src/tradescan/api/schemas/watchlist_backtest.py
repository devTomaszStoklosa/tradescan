"""Models of POST /api/watchlist-backtest."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.backtest import BacktestRulesIn, BacktestRulesOut, MetricsOut, SplitOut
from tradescan.api.schemas.common import UniverseIn
from tradescan.backtest.tickers import Period


class WatchlistBacktestIn(UniverseIn, BacktestRulesIn):
    benchmark: str | None = Field(
        None,
        description="Benchmark the market filter compares; omit for the watchlist's, else the configured benchmark",
    )


class TickerRunOut(BaseModel):
    ticker: str
    start: str
    end: str
    split: SplitOut | None = Field(
        description="This ticker's in-sample/out-of-sample split; null when its history is too short"
    )
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
    above_break_even_pct: float | None = Field(
        description="Share of the tickers above break-even; null for metrics without one"
    )


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
