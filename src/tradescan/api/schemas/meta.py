"""Models of GET /api/config: every settings section, rule and limit the UI offers."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.common import ParamSpecOut
from tradescan.backtest.rotation import Rebalance
from tradescan.backtest.walk_forward import WindowScheme
from tradescan.signals.base import Family


class SettingsSectionOut(BaseModel):
    name: str
    label: str
    params: list[ParamSpecOut]


class RuleOut(BaseModel):
    name: str
    label: str
    description: str = Field(description="The rule with the default parameters filled in")
    template: str = Field(description='The rule with {parameter} placeholders; format specs "", "g" and ".0%"')
    params: list[ParamSpecOut]


class FilterRuleOut(RuleOut):
    needs_benchmark: bool = Field(
        description="True when the filter compares the benchmark, which a backtest then loads"
    )


class PriorityRuleOut(RuleOut):
    needs_scan: bool = Field(
        description="True when the rule reads the scanner's settings (scoring, trend, scan.fresh_bars), "
        "which a run can override"
    )


class SweepLimitsOut(BaseModel):
    max_axes: int
    min_values: int
    max_values: int
    max_combinations: int
    sections: list[str] = Field(description="Settings sections whose parameters a sweep can change")
    fixed: list[str] = Field(description="section.name of settings a sweep cannot change")
    min_period_bars: int = Field(description="Bars each period needs for an in-sample/out-of-sample split")


class WalkForwardLimitsOut(BaseModel):
    max_runs: int = Field(
        description="Combinations times in-sample windows (the next one included) a walk-forward runs at most"
    )
    schemes: list[WindowScheme]
    default_scheme: WindowScheme
    metrics: list[str] = Field(description="Metrics an in-sample window can pick by, the highest first")
    default_metric: str
    fixed: list[str] = Field(description="section.name of settings a walk-forward cannot sweep")


class ConfigOut(BaseModel):
    version: str
    scan_period: str
    backtest_period: str
    benchmark: str
    sections: list[SettingsSectionOut] = Field(description="Adjustable settings; defaults come from settings.toml")
    families: list[Family]
    engines: list[str]
    entry_rules: list[RuleOut]
    exit_rules: list[RuleOut]
    filter_rules: list[FilterRuleOut] = Field(description="Entry filters; a backtest uses none unless it names them")
    default_entry: str
    default_exits: list[str]
    priority_rules: list[PriorityRuleOut] = Field(description="Priority rules of a portfolio backtest")
    default_priority: str
    ranking_rules: list[RuleOut] = Field(
        description="How a rotation ranks the tickers: the priority rules that read bars only"
    )
    default_ranking: str
    weight_rules: list[RuleOut] = Field(description="How a rotation's picks share the equity")
    default_weighting: str
    rebalances: list[Rebalance] = Field(description="How often a rotation rebalances")
    sweep: SweepLimitsOut
    walk_forward: WalkForwardLimitsOut
