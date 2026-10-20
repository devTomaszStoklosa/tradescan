"""Models several endpoints share: the request base, universes, signal filters, overrides and points."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradescan.params import ParamKind
from tradescan.signals.base import Direction, Family

ParamValueIn = float | list[float] | dict[str, float]
SettingsIn = dict[str, dict[str, ParamValueIn]]
SignalParamsIn = dict[str, float | list[float]]

SETTINGS_FIELD: SettingsIn = Field(
    default_factory=dict,
    description=(
        'Per-run overrides by settings section, e.g. {"risk": {"atr_mult": 3}}; see /api/config for every parameter'
    ),
)
SIGNAL_PARAMS_FIELD: dict[str, SignalParamsIn] = Field(
    default_factory=dict,
    description='Per-run signal parameters by signal name, e.g. {"connors_rsi2_long": {"oversold": 15}}',
)


class RequestModel(BaseModel):
    """Unknown fields are an error, so a misspelt or removed field never passes silently."""

    model_config = ConfigDict(extra="forbid")


class UniverseIn(RequestModel):
    watchlist: str | None = Field(None, description="Watchlist name, e.g. us_large")
    tickers: list[str] | None = Field(None, description="Ad-hoc tickers instead of a watchlist")

    @model_validator(mode="after")
    def _one_source(self) -> UniverseIn:
        if bool(self.watchlist) == bool(self.tickers):
            raise ValueError("Give either a watchlist or a list of tickers")
        return self


class SignalFilterIn(RequestModel):
    signals: list[str] = Field(default_factory=list, description="Signal names; empty means all")
    families: list[Family] = Field(default_factory=list)
    direction: Direction | None = Field(None, description="Omit for both directions")


class Point(BaseModel):
    time: str
    value: float


class ParamSpecOut(BaseModel):
    name: str
    kind: ParamKind
    label: str
    unit: str
    help: str
    default: int | float | list[float] | dict[str, float]
    minimum: float
    maximum: float
    step: float
    keys: list[str] | None = Field(None, description="Allowed keys of a weights parameter; null means any")


class ErrorOut(BaseModel):
    detail: str
