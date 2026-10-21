"""Models of POST /api/rotation-sweep."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.backtest import AppliedRuleOut, BacktestConfigOut, MetricsOut, SplitOut
from tradescan.api.schemas.common import RequestModel
from tradescan.api.schemas.rotation import RotationConfigOut, RotationSetupIn, RotationStatsOut
from tradescan.backtest.rotation_sweep import RotationSweepTarget
from tradescan.backtest.sweep import MAX_VALUES, MIN_VALUES
from tradescan.params import ParamKind


class RotationSweepAxisIn(RequestModel):
    target: RotationSweepTarget = Field(
        description="What holds the parameter: the ranking, the weighting or a settings section"
    )
    owner: str | None = Field(None, description="The settings section; omit for the ranking and the weighting rule")
    name: str = Field(description="The parameter, e.g. lookback or holdings")
    values: list[float] = Field(min_length=MIN_VALUES, max_length=MAX_VALUES, description="The values to try, in order")


class RotationSweepIn(RotationSetupIn):
    axes: list[RotationSweepAxisIn] = Field(
        min_length=1, description="One or two parameters; the first changes slowest"
    )


class RotationSweepAxisOut(BaseModel):
    target: RotationSweepTarget
    owner: str | None
    name: str
    key: str = Field(description="target[.owner].name")
    label: str
    unit: str
    kind: ParamKind
    current: float = Field(description="The value in the setup the sweep started from")
    values: list[float]


class RotationSweepCellOut(BaseModel):
    values: list[float] = Field(description="One value per axis, in axis order")
    in_sample: MetricsOut | None
    out_of_sample: MetricsOut | None
    in_sample_stats: RotationStatsOut | None
    out_of_sample_stats: RotationStatsOut | None
    error: str | None = Field(
        description="Why this combination could not run, e.g. a rule between two parameters or a lookback longer "
        "than a period"
    )


class RotationSweepOut(BaseModel):
    universe: str
    engine: str = Field(description="Sweeps run on this engine")
    start: str = Field(description="The setup's first rebalance with a pick")
    end: str
    config: BacktestConfigOut = Field(description="The setup's")
    rotation: RotationConfigOut = Field(description="The setup's")
    ranking: AppliedRuleOut = Field(description="The setup's")
    weighting: AppliedRuleOut = Field(description="The setup's")
    buy_hold_benchmark: str = Field(description="The benchmark buy & hold compares")
    split: SplitOut = Field(description="The split of the setup's run, the same for every combination")
    axes: list[RotationSweepAxisOut]
    cells: list[RotationSweepCellOut] = Field(description="Every combination; the first axis changes slowest")
    missing: list[str] = Field(description="Tickers without data")
