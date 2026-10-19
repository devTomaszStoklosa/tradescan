import pickle
from dataclasses import replace

import numpy as np
import pytest
from tests.synthetic import FakeProvider, FixedSignal, random_walk

from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.exits import TargetExit, TimeExit
from tradescan.backtest.filters import MarketFilter
from tradescan.backtest.metrics import compute_metrics
from tradescan.backtest.oos import MIN_PERIOD_BARS, SignalFrom, run_periods, split_history, split_index
from tradescan.backtest.sweep import MAX_COMBINATIONS, SweepAxis, SweepJob, SweepTarget, check_axes, grid
from tradescan.backtest.trade_rules import RuleChoice, TradeRules
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.config import Settings
from tradescan.parallel import ProcessRunner
from tradescan.services import BacktestRequest, SweepRequest, build_use_cases
from tradescan.signals import default_registry

CONFIG = BacktestConfig(commission_pct=0.1, slippage_pct=0.05)
RULES = TradeRules(exits=(TargetExit(), TimeExit(max_hold_bars=15)))


def _cerebro():
    pytest.importorskip("backtrader")
    from tradescan.backtest.cerebro import CerebroEngine

    return CerebroEngine()


# --- The split ---------------------------------------------------------------------------------


def test_split_index_keeps_the_last_share_out_of_sample():
    assert split_index(1000, 30) == 700
    assert split_index(1001, 30) == 700  # the out-of-sample period never gets less than its share
    assert split_index(1000, 10) == 900


def test_split_needs_enough_bars_in_both_periods():
    assert split_index(2 * MIN_PERIOD_BARS, 50) == MIN_PERIOD_BARS
    assert split_index(2 * MIN_PERIOD_BARS - 1, 50) is None
    assert split_index(500, 10) is None  # 50 out-of-sample bars


def test_split_history_reports_both_date_ranges():
    dates = random_walk(400).index
    split = split_history(dates, 25)
    assert split is not None and split.index == 300
    assert split.in_sample == (dates[0], dates[299])
    assert split.out_of_sample == (dates[300], dates[-1])
    assert split_history(dates[:100], 25) is None


def test_signal_from_drops_earlier_events_but_keeps_the_signal():
    df = random_walk(600, seed=3)
    signal = default_registry.create("connors_rsi2_long", {"oversold": 20})
    events = signal.events(df)
    late = SignalFrom(signal, 300)
    late_events = late.events(df)
    assert not late_events.iloc[:300].any()
    assert late_events.iloc[300:].equals(events.iloc[300:]) and events.iloc[300:].any()
    assert (late.name, late.direction, late.family, late.describe()) == (
        signal.name,
        signal.direction,
        signal.family,
        signal.describe(),
    )
    assert pickle.loads(pickle.dumps(late)).events(df).equals(late_events)  # worker processes can receive it


# --- Both periods --------------------------------------------------------------------------------


def test_in_sample_is_a_backtest_that_never_sees_later_bars():
    df = random_walk(1500, seed=5)
    signal = default_registry.create("donchian_breakout")
    periods = run_periods(VectorizedEngine(), "RW", df, signal, CONFIG, RULES, 1000)
    alone = VectorizedEngine().run("RW", df.iloc[:1000], signal, CONFIG, RULES)
    assert periods.in_sample == compute_metrics(alone.equity, alone.trades, df["close"].iloc[:1000])


def test_out_of_sample_starts_fresh_at_the_split():
    df = random_walk(1500, seed=5)
    signal = default_registry.create("donchian_breakout")
    late = VectorizedEngine().run("RW", df, SignalFrom(signal, 1000), CONFIG, RULES)
    assert late.trades and min(trade.signal_date for trade in late.trades) >= df.index[1000]
    assert late.equity.iloc[1000] == CONFIG.initial_equity  # nothing traded before the split
    periods = run_periods(VectorizedEngine(), "RW", df, signal, CONFIG, RULES, 1000)
    expected = compute_metrics(late.equity.iloc[1000:], late.trades, df["close"].iloc[1000:])
    assert periods.out_of_sample == expected
    assert periods.out_of_sample.buy_hold_pct == pytest.approx(
        (df["close"].iloc[-1] / df["close"].iloc[1000] - 1) * 100
    )


def test_out_of_sample_warms_indicators_up_on_the_earlier_bars():
    df = random_walk(1500, seed=6)
    signal = default_registry.create("golden_cross")  # needs a 200-bar average
    late = SignalFrom(signal, 1000).events(df)
    assert late.iloc[1000:].equals(signal.events(df).iloc[1000:])
    assert not signal.events(df.iloc[1000:]).iloc[:199].any()  # what a cold start would have missed


def test_engines_agree_on_both_periods():
    df = random_walk(1200, seed=8)
    for name in ("connors_rsi2_long", "ema_cross_down"):
        signal = default_registry.create(name)
        fast = run_periods(VectorizedEngine(), "RW", df, signal, CONFIG, RULES, 840)
        slow = run_periods(_cerebro(), "RW", df, signal, CONFIG, RULES, 840)
        for left, right in ((fast.in_sample, slow.in_sample), (fast.out_of_sample, slow.out_of_sample)):
            assert left.trades == right.trades > 0
            np.testing.assert_allclose(
                [left.total_return_pct, left.sharpe], [right.total_return_pct, right.sharpe], rtol=1e-6
            )


# --- The grid ------------------------------------------------------------------------------------


def _axis(name="oversold", values=(5, 10, 15), target=SweepTarget.SIGNAL, owner=""):
    return SweepAxis(target=target, name=name, values=tuple(values), owner=owner)


def test_grid_changes_the_first_axis_slowest():
    axes = [_axis(values=(5, 10)), _axis("target_r", (1.0, 2.0, 3.0), SweepTarget.EXIT, "target")]
    assert grid(axes) == [(5, 1.0), (5, 2.0), (5, 3.0), (10, 1.0), (10, 2.0), (10, 3.0)]
    assert axes[1].key == "exit.target.target_r" and axes[0].key == "signal.oversold"


@pytest.mark.parametrize(
    "axes, message",
    [
        ([], "1 or 2 parameters"),
        ([_axis(), _axis("a"), _axis("b")], "1 or 2 parameters"),
        ([_axis(), _axis()], "only once"),
        ([_axis(values=(5,))], "2 to 50 values"),
        ([_axis(values=range(51))], "2 to 50 values"),
        ([_axis(values=(5, 5))], "more than once"),
        ([_axis(values=range(15)), _axis("a", range(14))], f"at most {MAX_COMBINATIONS}"),
    ],
)
def test_grid_limits(axes, message):
    with pytest.raises(ValueError, match=message):
        check_axes(axes)


def test_sweep_job_is_picklable():
    job = SweepJob("RW", random_walk(200), 140)
    assert pickle.loads(pickle.dumps(job)).split == 140


# --- The sweep use case ----------------------------------------------------------------------------


@pytest.fixture
def frames():
    return {"AAA": random_walk(1500, seed=1), "TINY": random_walk(100, seed=2)}


def _use_cases(frames, runner=None):
    return build_use_cases(Settings(), FakeProvider(frames), runner=runner)


SETUP = BacktestRequest(ticker="aaa", signal="connors_rsi2_long", period="max")


def test_sweep_runs_every_combination_on_both_periods(frames):
    axes = (_axis(values=(10, 20)), _axis("target_r", (1.5, 2.0, 3.0), SweepTarget.EXIT, "target"))
    report = _use_cases(frames).sweep.run(SweepRequest(SETUP, axes))
    assert report.ticker == "AAA" and report.split.index == 1050
    assert [cell.values for cell in report.cells] == grid(axes)
    assert all(cell.periods is not None and cell.error is None for cell in report.cells)
    assert [(item.spec.label, item.spec.default) for item in report.parameters] == [
        ("Oversold level", 10.0),
        ("Distance", 2.0),
    ]

    # A cell is exactly the backtest of its combination, split the same way.
    cell = report.cells[4]  # oversold 20, target 2R
    signal = default_registry.create("connors_rsi2_long", {"oversold": 20})
    rules = TradeRules(exits=(TargetExit(target_r=2.0), TimeExit()))
    expected = run_periods(VectorizedEngine(), "AAA", frames["AAA"], signal, report.base.config, rules, 1050)
    assert cell.periods == expected


def test_sweep_values_follow_the_parameter_kind(frames):
    axes = (_axis("trend_period", (100.0, 150.0)),)
    report = _use_cases(frames).sweep.run(SweepRequest(SETUP, axes))
    assert report.parameters[0].axis.values == (100, 150) and isinstance(report.parameters[0].axis.values[0], int)


def test_a_combination_breaking_a_cross_field_rule_is_a_cell_error(frames):
    setup = BacktestRequest(ticker="AAA", signal="golden_cross", params={"slow": 60}, period="max")
    report = _use_cases(frames).sweep.run(SweepRequest(setup, (_axis("fast", (20, 40, 60, 80)),)))
    errors = [cell.error for cell in report.cells]
    assert errors[:2] == [None, None] and all("must be shorter" in error for error in errors[2:])
    assert report.cells[0].periods is not None and report.cells[3].periods is None


def test_sweep_settings_entry_and_account(frames):
    setup = BacktestRequest(ticker="AAA", signal="connors_rsi2_long", entry=RuleChoice("limit"), period="max")
    axes = (
        _axis("offset_atr", (0.25, 0.5), SweepTarget.ENTRY),
        _axis("atr_mult", (1.5, 2.5), SweepTarget.SETTINGS, "risk"),
    )
    report = _use_cases(frames).sweep.run(SweepRequest(setup, axes))
    assert len(report.cells) == 4 and all(cell.periods for cell in report.cells)
    account = (_axis("risk_pct", (0.5, 1.0), SweepTarget.SETTINGS, "account"),)
    assert len(_use_cases(frames).sweep.run(SweepRequest(SETUP, account)).cells) == 2


@pytest.mark.parametrize(
    "axis, message",
    [
        (_axis(values=(0, 10)), "oversold must be between 1 and 50"),
        (_axis("nope", (1, 2)), "unknown or fixed parameter 'nope'"),
        (_axis("trend_period", (100, 150.5)), "whole number"),
        (_axis("targets_r", (1, 2), SweepTarget.SETTINGS, "risk"), "not a single number"),
        (_axis("offset_atr", (0.1, 0.2), SweepTarget.EXIT, "limit"), "'limit' exit is not part of this backtest"),
        (
            _axis("period", (50, 100), SweepTarget.FILTER, "trend"),
            r"'trend' filter is not part of this backtest \(its filters: none\)",
        ),
        (_axis("fresh_bars", (1, 2), SweepTarget.SETTINGS, "scan"), "account, risk, backtest"),
        (_axis("oos_pct", (20, 30), SweepTarget.SETTINGS, "backtest"), "out-of-sample split"),
        (_axis(owner="target"), "takes no owner"),
    ],
)
def test_sweep_rejects_parameters_it_cannot_change(frames, axis, message):
    with pytest.raises(ValueError, match=message):
        _use_cases(frames).sweep.run(SweepRequest(SETUP, (axis,)))


def test_sweep_over_a_filter_compares_the_benchmark_in_every_combination(frames):
    frames = {**frames, "QQQ": random_walk(1600, seed=5)}
    provider = FakeProvider(frames)
    setup = replace(SETUP, filters=(RuleChoice("market"),), benchmark="qqq")
    axes = (_axis("period", (100, 200), SweepTarget.FILTER, "market"),)
    report = build_use_cases(Settings(), provider).sweep.run(SweepRequest(setup, axes))
    assert report.base.benchmark == "QQQ" and [call[0] for call in provider.calls] == [("AAA", "QQQ")]
    assert [(item.axis.key, item.spec.label, item.spec.default) for item in report.parameters] == [
        ("filter.market.period", "Benchmark SMA", 200)
    ]

    # A cell is the backtest of its combination, the benchmark's closes included.
    rules = TradeRules(filters=(MarketFilter(period=100),)).with_benchmark(frames["QQQ"]["close"])
    signal = default_registry.create("connors_rsi2_long")
    expected = run_periods(VectorizedEngine(), "AAA", frames["AAA"], signal, report.base.config, rules, 1050)
    assert report.cells[0].periods == expected


def test_sweep_needs_enough_history_to_split(frames):
    setup = BacktestRequest(ticker="TINY", signal="connors_rsi2_long", period="max")
    with pytest.raises(ValueError, match="too few to split"):
        _use_cases(frames).sweep.run(SweepRequest(setup, (_axis(),)))


def test_sweep_on_worker_processes_matches_one_process(frames):
    axes = (_axis(values=(10, 15, 20)), _axis("max_hold_bars", (10, 20), SweepTarget.EXIT, "time"))
    one = _use_cases(frames).sweep.run(SweepRequest(SETUP, axes))
    many = _use_cases(frames, ProcessRunner(workers=2, min_items=1)).sweep.run(SweepRequest(SETUP, axes))
    assert [cell.periods for cell in many.cells] == [cell.periods for cell in one.cells]


# --- The backtest reports both periods -------------------------------------------------------------


def test_backtest_reports_both_periods_for_every_engine(frames):
    pytest.importorskip("backtrader")
    request = BacktestRequest(
        ticker="AAA",
        signal="connors_rsi2_long",
        engines=("vectorized", "cerebro"),
        settings={"backtest": {"oos_pct": 20}},
        period="max",
    )
    report = _use_cases(frames).backtest.run(request)
    assert report.split is not None and report.split.index == 1200 and report.config.oos_pct == 20
    fast, slow = report.runs
    assert fast.periods is not None and slow.periods is not None
    assert fast.periods.out_of_sample.trades == slow.periods.out_of_sample.trades > 0
    close = frames["AAA"]["close"]
    assert fast.periods.in_sample.buy_hold_pct == pytest.approx((close.iloc[1199] / close.iloc[0] - 1) * 100)


def test_backtest_without_enough_history_has_no_split(frames):
    report = _use_cases(frames).backtest.run(BacktestRequest(ticker="TINY", signal="connors_rsi2_long", period="max"))
    assert report.split is None and report.runs[0].periods is None and report.runs[0].metrics is not None


def test_fixed_signal_events_respect_the_split():
    df = random_walk(400)
    late = SignalFrom(FixedSignal(positions=(10, 250, 300)), 260)
    assert list(np.flatnonzero(late.events(df).to_numpy())) == [300]
