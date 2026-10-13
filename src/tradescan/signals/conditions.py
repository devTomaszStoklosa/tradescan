"""Boolean building blocks for signal conditions."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _previous(value: pd.Series | float) -> pd.Series | float:
    return value.shift(1) if isinstance(value, pd.Series) else value


def crossed_above(series: pd.Series, level: pd.Series | float) -> pd.Series:
    """True on the bar where `series` moves from at/below `level` to above it."""
    return (series > level) & (series.shift(1) <= _previous(level))


def crossed_below(series: pd.Series, level: pd.Series | float) -> pd.Series:
    return (series < level) & (series.shift(1) >= _previous(level))


def rising_edge(condition: pd.Series) -> pd.Series:
    """True only on the first bar of each run of True values."""
    current = condition.astype(bool)
    return current & ~current.shift(1, fill_value=False)


def bars_since_last(events: pd.Series, window: int) -> int | None:
    """Bars since the most recent True within the last `window` bars (0 = last bar), else None."""
    recent = np.flatnonzero(events.to_numpy(dtype=bool)[-window:])
    if recent.size == 0:
        return None
    return min(window, len(events)) - 1 - int(recent[-1])
