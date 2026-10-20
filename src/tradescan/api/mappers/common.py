"""Helpers every mapper uses: finite floats, dates, series as points and parameter values."""

from __future__ import annotations

import math

import pandas as pd

from tradescan.api.schemas.common import ParamSpecOut, Point
from tradescan.backtest.rules import Rule
from tradescan.data.schema import bar_dates
from tradescan.params import ParamSpec, parameters_of
from tradescan.signals.base import Signal


def finite(value: float | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def day(timestamp: pd.Timestamp) -> str:
    return pd.Timestamp(timestamp).strftime("%Y-%m-%d")


def points(series: pd.Series) -> list[Point]:
    clean = series.dropna()
    return [
        Point(time=day(date), value=float(value))
        for date, value in zip(bar_dates(clean), clean.to_numpy(), strict=True)
    ]


def serializable(value: object) -> object:
    """Tuples become lists and mappings plain dicts, so pydantic can serialize them."""
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def param_spec_out(spec: ParamSpec) -> ParamSpecOut:
    return ParamSpecOut(
        name=spec.name,
        kind=spec.kind,
        label=spec.label,
        unit=spec.unit,
        help=spec.help,
        default=serializable(spec.default),
        minimum=spec.minimum,
        maximum=spec.maximum,
        step=spec.step,
        keys=list(spec.keys) if spec.keys is not None else None,
    )


def signal_params(signal: Signal | Rule) -> dict[str, float | list[float]]:
    """Current parameter values of a signal or rule."""
    return {spec.name: serializable(spec.default) for spec in parameters_of(signal)}  # type: ignore[misc]
