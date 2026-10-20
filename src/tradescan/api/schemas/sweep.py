"""Models of POST /api/sweep."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.backtest import BacktestSetupIn, BacktestSetupOut, MetricsOut, SplitOut
from tradescan.api.schemas.common import RequestModel
from tradescan.backtest.sweep import MAX_VALUES, MIN_VALUES, SweepTarget
from tradescan.params import ParamKind


class SweepAxisIn(RequestModel):
    target: SweepTarget = Field(
        description="What holds the parameter: the signal, the entry rule, an exit rule, an entry filter "
        "or a settings section"
    )
    owner: str | None = Field(
        None, description="The exit rule, entry filter or settings section; omit for the signal and the entry rule"
    )
    name: str = Field(description="The parameter, e.g. oversold")
    values: list[float] = Field(min_length=MIN_VALUES, max_length=MAX_VALUES, description="The values to try, in order")


class SweepIn(BacktestSetupIn):
    axes: list[SweepAxisIn] = Field(min_length=1, description="One or two parameters; the first changes slowest")


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
