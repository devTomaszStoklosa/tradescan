"""Models of POST /api/walk-forward."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.backtest import BacktestSetupOut, MetricsOut, TradeOut
from tradescan.api.schemas.common import Point
from tradescan.api.schemas.sweep import SweepAxisOut, SweepIn
from tradescan.backtest.walk_forward import DEFAULT_SELECTION_METRIC, WindowScheme


class WalkForwardIn(SweepIn):
    """`settings.walk_forward` sets the windows, the in-sample length and the trades a pick needs;
    `settings.backtest.oos_pct` has no effect, since the windows split the history."""

    scheme: WindowScheme = Field(
        WindowScheme.ROLLING,
        description="rolling: in-sample windows of fixed length that slide along; "
        "anchored: in-sample windows from the first bar",
    )
    metric: str = Field(
        DEFAULT_SELECTION_METRIC,
        description="Each in-sample window picks the combination with the highest value of this metric; "
        "/api/config lists them",
    )


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
    values: list[float] | None = Field(
        description="The picked combination, one value per axis; null when none qualified"
    )
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
        description="The bar where the next window took over: the next window's first bar, or later while a position "
        "of this window was still open; the last bar for the last window; null when the window had no part of its own"
    )
    out_of_sample: MetricsOut | None = Field(
        description="Of the window's own part of the stitched curve; null without one"
    )


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
    buy_hold: list[Point] = Field(
        description="Buy & hold from the first out-of-sample bar, scaled to the initial equity"
    )
    trades: list[TradeOut] = Field(description="Every out-of-sample trade, window after window")
