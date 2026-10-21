"""Rotation sweep: the same rotation over a grid of one or two parameters, in-sample and out-of-sample.

As for a backtest's sweep (`sweep`), a rotation sweep shows whether a result holds across nearby settings. Every
combination runs on the vectorized engine with `run_rotation_periods` at one split date, so every out-of-sample
result covers the same history, which no combination was tuned on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.priority import PriorityRule
from tradescan.backtest.rotation import RotationConfig, VectorizedRotationEngine, run_rotation_periods
from tradescan.backtest.rotation_metrics import RotationMetrics, rotation_metrics
from tradescan.backtest.weighting import WeightRule


class RotationSweepTarget(StrEnum):
    RANKING = "ranking"  # a parameter of the ranking rule
    WEIGHTING = "weighting"  # a parameter of the weighting rule
    SETTINGS = "settings"  # a setting of the section named by `owner`


@dataclass(frozen=True)
class RotationSweepAxis:
    target: RotationSweepTarget
    name: str
    values: tuple[float, ...]
    owner: str = ""  # the settings section; empty for the ranking and the weighting rule

    @property
    def key(self) -> str:
        """`target[.owner].name`, e.g. "ranking.lookback" or "settings.rotation.holdings"."""
        return ".".join(part for part in (self.target.value, self.owner, self.name) if part)


@dataclass(frozen=True)
class RotationSweepCase:
    """One combination's rotation inputs."""

    config: BacktestConfig
    rotation: RotationConfig
    ranking: PriorityRule
    weighting: WeightRule


@dataclass(frozen=True)
class RotationPeriodMetrics:
    in_sample: RotationMetrics
    out_of_sample: RotationMetrics


@dataclass(frozen=True)
class RotationSweepJob:
    """Runs one combination on both periods and keeps only their metrics, so worker processes send little back.
    A module-level callable, so worker processes can unpickle it."""

    frames: Mapping[str, pd.DataFrame]
    safe_frame: pd.DataFrame | None
    benchmark_close: pd.Series
    split: pd.Timestamp  # the first out-of-sample date

    def __call__(self, case: RotationSweepCase) -> RotationPeriodMetrics:
        periods = run_rotation_periods(
            VectorizedRotationEngine(),
            self.frames,
            case.config,
            case.rotation,
            case.ranking,
            case.weighting,
            self.safe_frame,
            self.split,
        )
        bars_per_year = case.config.bars_per_year
        return RotationPeriodMetrics(
            in_sample=rotation_metrics(periods.in_sample, self.benchmark_close, bars_per_year),
            out_of_sample=rotation_metrics(periods.out_of_sample, self.benchmark_close, bars_per_year),
        )
