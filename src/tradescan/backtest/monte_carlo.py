"""Monte Carlo of a run's trades: how much of a result is the luck of the order and of the sample.

A run's closed trades are resampled in R, and every resampled sequence is traded again with fixed-fractional
sizing: each trade changes equity by `risk_pct` percent times its R multiple. Two methods:

* shuffled: the same trades in a random order. Compounding does not depend on the order, so the final
  return is the same in every simulation; the drawdown and the losing streaks are what change;
* bootstrapped: as many trades drawn at random with replacement, which spreads the final return too.

The model leaves out what the engines add to R (the cap on position value, sizing from the equity at the
signal bar, a trade still open on the last bar), so its equity is not the run's equity. The run's own order
of trades under the same model is reported next to the simulations for that reason.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass

import numpy as np

from tradescan.backtest.base import Trade

MIN_TRADES = 2  # fewer closed trades leave nothing to resample
_CHUNK = 1000  # simulations per batch, so memory stays small however many are asked for

# Draws `count` sequences, one per row, from the R multiples.
Resampler = Callable[[np.random.Generator, np.ndarray, int], np.ndarray]


@dataclass(frozen=True)
class MonteCarloConfig:
    simulations: int = 1000
    ruin_drawdown_pct: float = 50.0  # a drawdown from the peak at least this deep counts as ruin
    seed: int = 0  # the same seed repeats the same simulations


@dataclass(frozen=True)
class Method:
    name: str
    label: str
    description: str
    resample: Resampler


def _shuffled(rng: np.random.Generator, r_multiples: np.ndarray, count: int) -> np.ndarray:
    return rng.permuted(np.tile(r_multiples, (count, 1)), axis=1)


def _bootstrapped(rng: np.random.Generator, r_multiples: np.ndarray, count: int) -> np.ndarray:
    return rng.choice(r_multiples, size=(count, r_multiples.size), replace=True)


METHODS: tuple[Method, ...] = (
    Method("shuffled", "Shuffled", "The same trades in a random order; the final return stays the same", _shuffled),
    Method("bootstrapped", "Bootstrapped", "As many trades drawn at random with replacement", _bootstrapped),
)


@dataclass(frozen=True)
class Percentiles:
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float


@dataclass(frozen=True)
class PathStats:
    """One sequence of trades traded with fixed-fractional sizing."""

    final_return_pct: float
    max_drawdown_pct: float  # negative, like `Metrics.max_drawdown_pct`
    longest_losing_streak: int


@dataclass(frozen=True)
class Distribution:
    """How the simulations of one method are spread."""

    method: Method
    final_return_pct: Percentiles
    max_drawdown_pct: Percentiles
    longest_losing_streak: Percentiles
    ruin_pct: float  # share of the simulations whose drawdown reached the ruin level


@dataclass(frozen=True)
class MonteCarlo:
    config: MonteCarloConfig
    risk_pct: float  # each trade changes equity by risk_pct percent times its R multiple
    trades: int  # closed trades resampled, and the length of every simulated sequence
    actual: PathStats  # the run's own order of trades
    methods: tuple[Distribution, ...]


def closed_r_multiples(trades: Iterable[Trade]) -> np.ndarray:
    """R multiples of the closed trades; trades without a planned risk (no R) are left out."""
    values = np.array([trade.r_multiple for trade in trades if trade.is_closed], dtype=float)
    return values[np.isfinite(values)]


def simulate(
    r_multiples: np.ndarray, risk_pct: float, config: MonteCarloConfig, methods: Sequence[Method] = METHODS
) -> MonteCarlo | None:
    """Every method's simulations of `r_multiples`; None with fewer than MIN_TRADES trades."""
    r_multiples = np.asarray(r_multiples, dtype=float)
    if r_multiples.size < MIN_TRADES:
        return None
    final, drawdown, streak = _paths(r_multiples[np.newaxis, :], risk_pct)
    return MonteCarlo(
        config=config,
        risk_pct=risk_pct,
        trades=int(r_multiples.size),
        actual=PathStats(float(final[0]), float(drawdown[0]), int(streak[0])),
        methods=tuple(_distribution(method, r_multiples, risk_pct, config) for method in methods),
    )


def _distribution(method: Method, r_multiples: np.ndarray, risk_pct: float, config: MonteCarloConfig) -> Distribution:
    # Each method starts from the seed, so adding or reordering methods never changes another's results.
    rng = np.random.default_rng(config.seed)
    batches = [_paths(method.resample(rng, r_multiples, count), risk_pct) for count in _batches(config.simulations)]
    final, drawdown, streak = (np.concatenate(values) for values in zip(*batches, strict=True))
    return Distribution(
        method=method,
        final_return_pct=_percentiles(final),
        max_drawdown_pct=_percentiles(drawdown),
        longest_losing_streak=_percentiles(streak),
        ruin_pct=float((drawdown <= -config.ruin_drawdown_pct).mean() * 100.0),
    )


def _batches(simulations: int) -> Iterator[int]:
    for start in range(0, simulations, _CHUNK):
        yield min(_CHUNK, simulations - start)


def _paths(r_multiples: np.ndarray, risk_pct: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Final return %, max drawdown % and longest losing streak of every row. Equity cannot fall below zero,
    and once at zero it stays there."""
    growth = np.maximum(1.0 + risk_pct / 100.0 * r_multiples, 0.0)
    equity = np.cumprod(np.hstack([np.ones((r_multiples.shape[0], 1)), growth]), axis=1)
    peak = np.maximum.accumulate(equity, axis=1)  # at least the starting 1, so never zero
    drawdown = (equity / peak - 1.0).min(axis=1) * 100.0
    return (equity[:, -1] - 1.0) * 100.0, drawdown, _longest_run(r_multiples < 0)


def _longest_run(flags: np.ndarray) -> np.ndarray:
    """The longest run of consecutive True values in every row."""
    current = np.zeros(flags.shape[0], dtype=int)
    longest = np.zeros_like(current)
    for column in flags.T:
        current = np.where(column, current + 1, 0)
        np.maximum(longest, current, out=longest)
    return longest


def _percentiles(values: np.ndarray) -> Percentiles:
    p5, p25, p50, p75, p95 = (float(value) for value in np.percentile(values, (5, 25, 50, 75, 95)))
    return Percentiles(p5=p5, p25=p25, p50=p50, p75=p75, p95=p95)
