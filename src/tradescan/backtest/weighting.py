"""Weighting rules: how a rotation shares its equity among the tickers it picks at a rebalance.

A rule gives every bar of a ticker a causal raw weight once per run (`raw`). At a rebalance the picks share their
slots in proportion to their raw weights (`book_weights`), so a full book of `holdings` picks sums to 100% of
equity and each pick averages one slot. A ticker without a raw weight, e.g. while a lookback warms up, cannot be
picked. New rules plug in with `@weight_rules.register`.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradescan.backtest.rules import Bars, Rule, RuleRegistry
from tradescan.params import param


class WeightRule(Rule):
    @abstractmethod
    def raw(self, bars: Bars) -> np.ndarray:
        """Causal: the ticker's raw weight at each close, above 0; NaN where there is none."""


weight_rules: RuleRegistry[WeightRule] = RuleRegistry("weighting")


@weight_rules.register
@dataclass(frozen=True)
class EqualWeight(WeightRule):
    name = "equal"
    label = "Equal"
    description = "Every pick gets one slot"

    def raw(self, bars: Bars) -> np.ndarray:
        return np.ones(len(bars))


@weight_rules.register
@dataclass(frozen=True)
class InverseVolatilityWeight(WeightRule):
    lookback: int = param(
        63, minimum=2, maximum=1000, step=1, label="Volatility lookback", unit="bars",
        help="Daily returns over this many bars give each pick's volatility",
    )
    name = "inverse_volatility"
    label = "Inverse volatility"
    description = "Picks weighted by 1 / the volatility of their daily returns over {lookback} bars"

    def raw(self, bars: Bars) -> np.ndarray:
        """A ticker whose closes did not move over the lookback has no weight."""
        returns = pd.Series(bars.close).pct_change()
        volatility = returns.rolling(self.lookback).std(ddof=1).to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            weights = 1.0 / volatility
        weights[~np.isfinite(weights)] = np.nan
        return weights


def book_weights(raw: np.ndarray, holdings: int) -> np.ndarray:
    """The picks' shares of equity: proportional to their raw weights, `len(raw) / holdings` in total."""
    return raw / raw.sum() * len(raw) / holdings


DEFAULT_WEIGHTING = EqualWeight.name
