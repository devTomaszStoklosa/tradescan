"""Building blocks of the entry filters, entry rules and exit rules that both backtest engines execute.

A rule is a frozen dataclass whose numbers are declared with `tradescan.params.param`, like a signal's,
so the API publishes them and the web UI builds their fields. Rules work on numpy arrays (`Bars`) and
compute their levels once per run; the engines only execute the orders the rules ask for, so a new
rule never needs engine changes.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import ClassVar, Generic, TypeVar

import numpy as np
import pandas as pd

from tradescan.indicators import atr
from tradescan.params import Overrides, ParamSpec, parameters_of, with_overrides


@dataclass(frozen=True, eq=False)
class Bars:
    """One ticker's prices, volume and ATR as float arrays, aligned with its DataFrame and its dates."""

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    atr: np.ndarray
    dates: pd.DatetimeIndex

    @classmethod
    def from_frame(cls, df: pd.DataFrame, atr_period: int) -> Bars:
        values = (df[column].to_numpy(dtype=float) for column in ("open", "high", "low", "close", "volume"))
        return cls(*values, atr=atr(df, atr_period).to_numpy(dtype=float), dates=pd.DatetimeIndex(df.index))

    def __len__(self) -> int:
        return len(self.close)


class Rule(ABC):
    """A named rule with declared parameters.

    Subclasses are frozen dataclasses. `description` is a template over their parameters, with the
    same format specs as signal descriptions ("", "g" and ".0%"), so the web UI can fill it in too.
    """

    name: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str]

    @classmethod
    def parameters(cls) -> tuple[ParamSpec, ...]:
        return parameters_of(cls)

    def describe(self) -> str:
        """The rule with this instance's parameter values filled in."""
        return self.description.format(**{spec.name: spec.default for spec in parameters_of(self)})


R = TypeVar("R", bound=Rule)


class RuleRegistry(Generic[R]):
    """Rules of one kind by name, in registration order (the order the UI offers them)."""

    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._classes: dict[str, type[R]] = {}

    def register(self, cls: type[R]) -> type[R]:
        if cls.name in self._classes:
            raise ValueError(f"Duplicate {self._kind} rule name: {cls.name}")
        self._classes[cls.name] = cls
        return cls

    def names(self) -> list[str]:
        return list(self._classes)

    def classes(self) -> list[type[R]]:
        return list(self._classes.values())

    def create(self, name: str, params: Overrides | None = None) -> R:
        """A rule with its default parameters, or with `params` validated against their declared ranges."""
        try:
            cls = self._classes[name]
        except KeyError:
            raise ValueError(f"Unknown {self._kind} rule '{name}'. Use: {', '.join(self._classes)}") from None
        return with_overrides(cls(), params, owner=name)
