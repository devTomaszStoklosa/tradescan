"""Map settings sections and rules to the models of GET /api/config."""

from __future__ import annotations

from tradescan.api.mappers.common import param_spec_out
from tradescan.api.schemas.meta import FilterRuleOut, PriorityRuleOut, RuleOut, SettingsSectionOut
from tradescan.backtest.filters import EntryFilter
from tradescan.backtest.priority import PriorityRule
from tradescan.backtest.rules import Rule
from tradescan.config import SettingsSection


def section_out(section: SettingsSection) -> SettingsSectionOut:
    return SettingsSectionOut(
        name=section.name, label=section.label, params=[param_spec_out(spec) for spec in section.parameters]
    )


def rule_out(rule: type[Rule]) -> RuleOut:
    return RuleOut(
        name=rule.name,
        label=rule.label,
        description=rule().describe(),
        template=rule.description,
        params=[param_spec_out(spec) for spec in rule.parameters()],
    )


def filter_rule_out(rule: type[EntryFilter]) -> FilterRuleOut:
    return FilterRuleOut(**rule_out(rule).model_dump(), needs_benchmark=rule.needs_benchmark)


def priority_rule_out(rule: type[PriorityRule]) -> PriorityRuleOut:
    return PriorityRuleOut(**rule_out(rule).model_dump(), needs_scan=rule.needs_scan)
