"""Signal abstraction shared by the scanner, edge statistics and both backtest engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import ClassVar

import pandas as pd

from tradescan.signals.conditions import rising_edge


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> float:
        return 1.0 if self is Direction.LONG else -1.0


class Family(StrEnum):
    TREND = "trend"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    MEAN_REVERSION = "mean_reversion"
    VOLUME = "volume"
    PATTERN = "pattern"


class Signal(ABC):
    """A rule evaluated on the close of each bar.

    Subclasses implement `condition`. `events` turns it into one-bar events (the first bar on which
    the condition holds), so every signal is counted, scored and backtested the same way.
    """

    name: ClassVar[str]
    family: ClassVar[Family]
    direction: ClassVar[Direction]
    description: ClassVar[str]

    @abstractmethod
    def condition(self, df: pd.DataFrame) -> pd.Series:
        """Boolean Series aligned with `df.index`, causal (no future data)."""

    def events(self, df: pd.DataFrame) -> pd.Series:
        return rising_edge(self.condition(df)).rename(self.name)
