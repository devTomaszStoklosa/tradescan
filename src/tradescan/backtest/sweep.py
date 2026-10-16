"""Parameter sweep: the same backtest over a grid of one or two parameters, in-sample and out-of-sample.

A sweep shows whether a result holds across nearby settings or comes from one lucky setting. Every
combination runs on the vectorized engine, split by `oos.run_periods`, so its out-of-sample result
comes from history that no combination was tuned on.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.oos import PeriodMetrics, run_periods
from tradescan.backtest.trade_rules import TradeRules
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.signals.base import Signal

MAX_AXES = 2
MIN_VALUES = 2
MAX_VALUES = 50
MAX_COMBINATIONS = 200  # keeps a sweep to seconds; each combination is two backtests


class SweepTarget(StrEnum):
    SIGNAL = "signal"  # a parameter of the signal
    ENTRY = "entry"  # a parameter of the entry rule
    EXIT = "exit"  # a parameter of the exit rule named by `owner`
    FILTER = "filter"  # a parameter of the entry filter named by `owner`
    SETTINGS = "settings"  # a setting of the section named by `owner`


@dataclass(frozen=True)
class SweepAxis:
    target: SweepTarget
    name: str
    values: tuple[float, ...]
    owner: str = ""  # the exit rule, entry filter or settings section; empty for the signal and the entry rule

    @property
    def key(self) -> str:
        """`target[.owner].name`, e.g. "signal.oversold" or "exit.target.target_r"."""
        return ".".join(part for part in (self.target.value, self.owner, self.name) if part)


def check_axes(axes: Sequence[SweepAxis]) -> None:
    if not 1 <= len(axes) <= MAX_AXES:
        raise ValueError(f"A sweep needs 1 or {MAX_AXES} parameters, got {len(axes)}")
    keys = [axis.key for axis in axes]
    if len(set(keys)) != len(keys):
        raise ValueError(f"A parameter can be swept only once: {keys[0]}")
    for axis in axes:
        if not MIN_VALUES <= len(axis.values) <= MAX_VALUES:
            raise ValueError(f"{axis.key} needs {MIN_VALUES} to {MAX_VALUES} values, got {len(axis.values)}")
        if len(set(axis.values)) != len(axis.values):
            raise ValueError(f"{axis.key} lists a value more than once")
    combinations = 1
    for axis in axes:
        combinations *= len(axis.values)
    if combinations > MAX_COMBINATIONS:
        raise ValueError(f"{combinations} combinations is too many; a sweep runs at most {MAX_COMBINATIONS}")


def grid(axes: Sequence[SweepAxis]) -> list[tuple[float, ...]]:
    """Every combination of the axes' values; the first axis changes slowest."""
    check_axes(axes)
    return list(itertools.product(*(axis.values for axis in axes)))


@dataclass(frozen=True)
class SweepCase:
    """One combination's backtest inputs."""

    signal: Signal
    rules: TradeRules
    config: BacktestConfig


@dataclass(frozen=True)
class SweepJob:
    """Runs one combination on both periods. A module-level callable, so worker processes can unpickle it."""

    ticker: str
    df: pd.DataFrame
    split: int

    def __call__(self, case: SweepCase) -> PeriodMetrics:
        return run_periods(VectorizedEngine(), self.ticker, self.df, case.signal, case.config, case.rules, self.split)
