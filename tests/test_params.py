import re
from dataclasses import fields
from pathlib import Path

import pytest
from tests.synthetic import random_walk

from tradescan.backtest.entries import entry_rules
from tradescan.backtest.exits import exit_rules
from tradescan.backtest.filters import entry_filters
from tradescan.backtest.trade_rules import RuleCatalog, RuleChoice, TradeRules
from tradescan.config import Settings, adjustable_sections, load_settings
from tradescan.params import ParamKind, parameters_of, validate, with_overrides
from tradescan.signals import Family, default_registry

ALL_SIGNALS = default_registry.names()
ALL_RULES = [*entry_rules.classes(), *exit_rules.classes(), *entry_filters.classes()]

# Numeric settings that never change a result, so they are deliberately not adjustable per run.
NOT_PARAMETERS = {("data", "cache_ttl_hours")}

# Annotation (a string under `from __future__ import annotations`) -> the kind its param() must have.
KIND_OF_ANNOTATION = {
    "int": ParamKind.INT,
    "float": ParamKind.FLOAT,
    "tuple[int, ...]": ParamKind.INT_LIST,
    "tuple[float, ...]": ParamKind.FLOAT_LIST,
    "dict[str, float]": ParamKind.WEIGHTS,
}

PLACEHOLDER = re.compile(r"\{(\w+)(?::([^}]*))?\}")


def _assert_numeric_fields_declared(obj, owner, skip=frozenset()):
    declared = {spec.name: spec for spec in parameters_of(obj)}
    for item in fields(obj):
        if item.type not in KIND_OF_ANNOTATION or (owner, item.name) in skip:
            continue
        assert item.name in declared, f"{owner}.{item.name} has no param() declaration, so the UI cannot offer it"
        assert declared[item.name].kind is KIND_OF_ANNOTATION[item.type], (
            f"{owner}.{item.name}: default type != annotation"
        )
    validate(obj, owner)  # defaults lie inside their own ranges


# --- The rule: every setting that changes a result is adjustable --------------------------------


@pytest.mark.parametrize("name", ALL_SIGNALS)
def test_every_signal_setting_is_a_declared_parameter(name):
    signal = default_registry.create(name)
    _assert_numeric_fields_declared(signal, name)
    assert signal.parameters(), f"{name} has nothing to adjust"


def test_every_result_setting_is_a_declared_parameter():
    settings = Settings()
    for item in fields(settings):
        _assert_numeric_fields_declared(getattr(settings, item.name), item.name, skip=NOT_PARAMETERS)


@pytest.mark.parametrize("rule", ALL_RULES, ids=lambda rule: rule.name)
def test_every_entry_and_exit_rule_setting_is_a_declared_parameter(rule):
    _assert_numeric_fields_declared(rule(), rule.name)


def _assert_description_shows_every_parameter(obj, name):
    placeholders = PLACEHOLDER.findall(obj.description)
    kinds = {spec.name: spec.kind for spec in obj.parameters()}
    assert {key for key, _ in placeholders} == set(kinds)
    for key, format_spec in placeholders:
        # Python prints 2.0 as "2.0" but the UI as "2", so floats need "g" (or ".0%") to read the same in both.
        allowed = {"g", ".0%"} if kinds[key] is ParamKind.FLOAT else {""}
        assert format_spec in allowed, f"{name}: {{{key}:{format_spec}}}"
    text = obj.describe()
    assert "{" not in text and "}" not in text


@pytest.mark.parametrize("name", ALL_SIGNALS)
def test_descriptions_show_every_parameter_in_a_format_the_ui_renders(name):
    _assert_description_shows_every_parameter(default_registry.create(name), name)


@pytest.mark.parametrize("rule", ALL_RULES, ids=lambda rule: rule.name)
def test_rule_descriptions_show_every_parameter_in_a_format_the_ui_renders(rule):
    _assert_description_shows_every_parameter(rule(), rule.name)


# --- Overrides -----------------------------------------------------------------------------------


def test_signal_overrides_are_validated_and_leave_the_default_untouched():
    signal = default_registry.create("connors_rsi2_long")
    changed = with_overrides(signal, {"oversold": 15, "rsi_period": 3.0}, owner="connors_rsi2_long")
    assert (changed.oversold, changed.rsi_period) == (15.0, 3) and isinstance(changed.rsi_period, int)
    assert changed.describe().startswith("RSI(3) < 15 while price is above SMA(200)")
    assert signal.oversold == 10.0
    for values, message in [
        ({"oversold": 0}, "between 1 and 50"),
        ({"rsi_period": 2.5}, "whole number"),
        ({"oversold": "x"}, "must be a number"),
        ({"oversold": True}, "must be a number"),
        ({"oversold": float("nan")}, "must be a number"),
        ({"overbought": 90}, "unknown or fixed"),
    ]:
        with pytest.raises(ValueError, match=message):
            with_overrides(signal, values, owner="connors_rsi2_long")


def test_cross_field_rules():
    with pytest.raises(ValueError, match="shorter"):
        default_registry.create("golden_cross", {"fast": 200})
    with pytest.raises(ValueError, match="shorter"):
        default_registry.create("macd_cross_up", {"slow": 10})
    with pytest.raises(ValueError, match="slow_period"):
        Settings().with_overrides({"trend": {"fast_period": 250}})
    with pytest.raises(ValueError, match="weights"):
        Settings().with_overrides({"trend": {"rs_weights": [1.0]}})
    with pytest.raises(ValueError, match="risk_off_breadth"):
        Settings().with_overrides({"regime": {"risk_off_breadth": 65}})


def test_list_and_weight_parameters():
    settings = Settings().with_overrides(
        {
            "risk": {"targets_r": 1.5},
            "trend": {"rs_periods": [21, 63], "rs_weights": [0.5, 0.5]},
            "scoring": {"family_weights": {"breakout": 3}, "signal_weights": {"golden_cross": 2}},
        }
    )
    assert settings.risk.targets_r == (1.5,)
    assert settings.trend.rs_periods == (21, 63)
    assert settings.scoring.family_weights["breakout"] == 3.0 and settings.scoring.family_weights["trend"] == 1.0
    assert settings.scoring.signal_weights == {"golden_cross": 2.0}
    assert Settings().scoring.family_weights["breakout"] == 1.5
    for overrides, message in [
        ({"trend": {"rs_periods": [10.5, 20], "rs_weights": [0.5, 0.5]}}, "whole number"),
        ({"risk": {"targets_r": []}}, "at least one"),
        ({"risk": {"targets_r": [2, 99]}}, "between"),
        ({"scoring": {"family_weights": {"nope": 1}}}, "unknown key"),
        ({"scoring": {"family_weights": 2}}, "mapping"),
    ]:
        with pytest.raises(ValueError, match=message):
            Settings().with_overrides(overrides)


def test_only_declared_settings_can_be_overridden():
    with pytest.raises(ValueError, match="cache_dir"):
        Settings().with_overrides({"data": {"cache_dir": "elsewhere"}})
    with pytest.raises(ValueError, match="period"):
        Settings().with_overrides({"backtest": {"period": 1}})
    with pytest.raises(ValueError, match="unknown settings section"):
        Settings().with_overrides({"nope": {"x": 1}})


def test_settings_file_values_are_range_checked(tmp_path: Path):
    path = tmp_path / "settings.toml"
    path.write_text("[risk]\natr_mult = 0\n")
    with pytest.raises(ValueError, match=r"\[risk\]\.atr_mult"):
        load_settings(path)
    path.write_text("[trend]\nrs_periods = [21, 63]\nrs_weights = [0.5, 0.5]\n")
    assert load_settings(path).trend.rs_periods == (21, 63)


def test_sections_publish_the_configured_values_as_defaults():
    settings = Settings().with_overrides({"risk": {"atr_mult": 3}})
    sections = {
        section.name: {spec.name: spec for spec in section.parameters} for section in adjustable_sections(settings)
    }
    assert sections["risk"]["atr_mult"].default == 3.0
    assert "data" not in sections


def test_rule_catalog_builds_validated_rules():
    catalog = RuleCatalog()
    assert catalog.build() == TradeRules()
    rules = catalog.build(RuleChoice("stop", {"offset_atr": 0.25}), [RuleChoice("target", {"target_r": 3})])
    assert rules.entry.offset_atr == 0.25 and [rule.target_r for rule in rules.exits] == [3.0]
    assert catalog.build(exits=[]).exits == ()
    for entry, exits, message in [
        (RuleChoice("nope"), None, "Unknown entry rule 'nope'. Use: next_open, stop, limit"),
        (None, [RuleChoice("nope")], "Unknown exit rule"),
        (RuleChoice("limit", {"valid_bars": 21}), None, "between 1 and 20"),
        (RuleChoice("next_open", {"offset_atr": 1}), None, "unknown or fixed"),
        (None, [RuleChoice("time"), RuleChoice("time")], "more than once"),
    ]:
        with pytest.raises(ValueError, match=message):
            catalog.build(entry, exits)


def test_old_target_and_time_settings_are_gone():
    with pytest.raises(ValueError, match="target_r"):
        Settings().with_overrides({"backtest": {"target_r": 3}})


def test_parameters_change_signal_events():
    df = random_walk()
    strict = default_registry.create("connors_rsi2_long").events(df).sum()
    loose = default_registry.create("connors_rsi2_long", {"oversold": 30}).events(df).sum()
    assert loose > strict > 0


def test_registry_checks_parameters_even_for_signals_a_filter_leaves_out():
    with pytest.raises(ValueError, match="unknown signal"):
        default_registry.select(params={"nope": {}})
    with pytest.raises(ValueError, match="between"):
        default_registry.select(families={Family.TREND}, params={"connors_rsi2_long": {"oversold": 0}})
    trend = default_registry.select(families={Family.TREND}, params={"golden_cross": {"fast": 20}})
    assert next(signal for signal in trend if signal.name == "golden_cross").fast == 20
