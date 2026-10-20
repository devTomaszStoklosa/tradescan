import math
import pickle
from dataclasses import replace
from itertools import pairwise

import pandas as pd
import pytest

import tradescan.services.walk_forward as walk_forward_service
from tests.synthetic import FakeProvider, FixedSignal, random_walk
from tradescan.backtest.base import BacktestConfig, ExitReason
from tradescan.backtest.exits import TimeExit
from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.oos import SignalBetween, SignalFrom, run_periods
from tradescan.backtest.sweep import SweepAxis, SweepCase, SweepTarget
from tradescan.backtest.trade_rules import TradeRules
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.backtest.walk_forward import (
    InSampleJob,
    Span,
    Window,
    WindowPlan,
    WindowScheme,
    efficiency,
    in_sample_metrics,
    pick,
    plan_windows,
    stitch,
)
from tradescan.config import Settings
from tradescan.parallel import ProcessRunner
from tradescan.services.backtest import BacktestRequest
from tradescan.services.composition import build_use_cases
from tradescan.services.walk_forward import WalkForwardRequest

# --- Windows -----------------------------------------------------------------------------------------


def test_rolling_windows_end_on_the_last_bar_after_in_sample_windows_of_fixed_length():
    plan = plan_windows(1000, 4, 3.0, WindowScheme.ROLLING)  # 142-bar windows after 426-bar in-sample windows
    assert [window.out_of_sample for window in plan.windows] == [
        Span(432, 574),
        Span(574, 716),
        Span(716, 858),
        Span(858, 1000),
    ]
    assert [window.in_sample for window in plan.windows] == [
        Span(6, 432),
        Span(148, 574),
        Span(290, 716),
        Span(432, 858),
    ]
    assert plan.next_in_sample == Span(574, 1000)
    assert plan.start == 432
    assert plan.in_samples[-1] == plan.next_in_sample
    assert len(plan.in_samples) == 5


def test_anchored_in_sample_windows_start_on_the_first_bar():
    plan = plan_windows(1000, 4, 3.0, WindowScheme.ANCHORED)
    assert [window.in_sample for window in plan.windows] == [Span(0, 432), Span(0, 574), Span(0, 716), Span(0, 858)]
    assert plan.next_in_sample == Span(0, 1000)


def test_a_fractional_ratio_rounds_the_in_sample_window_down():
    plan = plan_windows(1000, 2, 2.5, WindowScheme.ROLLING)  # 222-bar windows, 555-bar in-sample windows
    assert plan.windows[0] == Window(Span(1, 556), Span(556, 778))
    assert plan.windows[1].out_of_sample == Span(778, 1000)


def test_every_window_needs_enough_bars():
    with pytest.raises(ValueError, match=r"400 bars are too few for 5 windows .* at least 480 bars"):
        plan_windows(400, 5, 3.0, WindowScheme.ROLLING)
    assert plan_windows(480, 5, 3.0, WindowScheme.ROLLING).windows[0].out_of_sample.bars == 60


# --- Picking -----------------------------------------------------------------------------------------


def _metrics(sharpe: float, trades: int = 20) -> Metrics:
    return Metrics(
        total_return_pct=1.0, cagr_pct=1.0, sharpe=sharpe, sortino=1.0, max_drawdown_pct=-1.0, trades=trades,
        win_rate_pct=50.0, profit_factor=1.0, expectancy_r=0.1, sqn=1.0, exposure_pct=10.0, buy_hold_pct=5.0,
    )  # fmt: skip


def test_pick_takes_the_highest_value_among_combinations_with_enough_trades():
    results = [_metrics(1.0), None, _metrics(3.0, trades=5), _metrics(math.nan), _metrics(2.0), _metrics(2.0)]
    assert pick(results, "sharpe", min_trades=10) == 4  # the tie goes to the first
    assert pick(results, "sharpe", min_trades=0) == 2
    assert pick([_metrics(math.inf, trades=12), _metrics(9.0)], "sharpe", 10) == 0
    assert pick(results, "sharpe", min_trades=100) is None
    assert pick([], "sharpe", 0) is None


def test_efficiency_compares_the_stitched_cagr_with_the_average_in_sample_cagr_of_the_picks():
    def cagr(value):
        return replace(_metrics(1.0), cagr_pct=value)

    assert efficiency(cagr(3.0), [cagr(4.0), cagr(8.0), cagr(math.nan)]) == pytest.approx(0.5)
    assert math.isnan(efficiency(cagr(3.0), [cagr(-1.0), cagr(1.0)]))
    assert math.isnan(efficiency(cagr(3.0), []))


# --- Runs on the windows -----------------------------------------------------------------------------


def test_signal_between_keeps_only_the_events_of_its_window():
    df = random_walk(100)
    events = SignalBetween(FixedSignal(positions=(5, 20, 39, 40, 70)), 20, 40).events(df)
    assert list(events.to_numpy().nonzero()[0]) == [20, 39]


def test_an_in_sample_window_from_the_first_bar_is_the_in_sample_period_of_a_split():
    df, signal, config = random_walk(800), FixedSignal(positions=tuple(range(30, 800, 25))), BacktestConfig()
    case = SweepCase(signal, TradeRules(), config)
    expected = run_periods(VectorizedEngine(), "RW", df, signal, config, TradeRules(), 560).in_sample
    assert in_sample_metrics(VectorizedEngine(), "RW", df, case, Span(0, 560)) == expected


def test_a_later_in_sample_window_trades_from_its_start_on_bars_up_to_its_end():
    df, config = random_walk(800), BacktestConfig()
    case = SweepCase(FixedSignal(positions=(100, 300, 450, 700)), TradeRules(), config)
    metrics = in_sample_metrics(VectorizedEngine(), "RW", df, case, Span(250, 600))
    result = VectorizedEngine().run("RW", df.iloc[:600], SignalFrom(case.signal, 250), config, TradeRules())
    assert [trade.signal_date for trade in result.trades] == [df.index[300], df.index[450]]
    assert metrics == compute_metrics(result.equity.iloc[250:], result.trades, df["close"].iloc[250:600])


def test_in_sample_job_is_picklable():
    job = InSampleJob("RW", random_walk(200), (Span(0, 100), Span(50, 150)))
    assert pickle.loads(pickle.dumps(job)).spans == (Span(0, 100), Span(50, 150))


# --- Stitching ---------------------------------------------------------------------------------------

PLAN = WindowPlan(
    scheme=WindowScheme.ROLLING,
    windows=(
        Window(Span(0, 400), Span(400, 600)),
        Window(Span(200, 600), Span(600, 800)),
        Window(Span(400, 800), Span(800, 1000)),
    ),
    next_in_sample=Span(600, 1000),
)
# A distant stop, so only the time exit closes a trade.
WIDE_STOP = BacktestConfig(atr_mult=20.0, max_position_pct=100.0)


def _case(positions, hold=20):
    return SweepCase(FixedSignal(positions=positions), TradeRules(exits=(TimeExit(max_hold_bars=hold),)), WIDE_STOP)


def test_windows_join_into_one_curve_that_carries_the_equity_over():
    df = random_walk(1000)
    run = stitch(VectorizedEngine(), "RW", df, PLAN, [_case((450, 520)), _case((650,)), _case((850, 900))], 100_000.0)
    assert list(run.equity.index) == list(df.index[400:])
    assert run.equity.iloc[0] == 100_000.0
    assert [(segment.start, segment.end) for segment in run.segments] == [(400, 600), (600, 800), (800, 999)]
    for segment, after in pairwise(run.segments):
        # The next window starts with the equity this one ended with, so the curve has no jump.
        assert after.equity.iloc[0] == segment.equity.iloc[-1] == run.equity.loc[df.index[segment.end]]
    assert [len(segment.trades) for segment in run.segments] == [2, 1, 2]
    assert len(run.trades) == 5
    assert run.equity.iloc[-1] == pytest.approx(100_000.0 + sum(trade.pnl for trade in run.trades))

    # Every window is the backtest of its pick, started with the equity carried over.
    second = run.segments[1]
    config = replace(WIDE_STOP, initial_equity=run.segments[0].equity.iloc[-1])
    alone = VectorizedEngine().run(
        "RW", df, SignalBetween(FixedSignal(positions=(650,)), 600, 800), config, _case(()).rules
    )
    assert second.trades == alone.trades


def test_a_position_open_at_a_window_end_runs_to_its_exit_before_the_next_window_trades():
    df = random_walk(1000)
    picks = [_case((590,), hold=30), _case((605, 650)), _case((850,))]
    run = stitch(VectorizedEngine(), "RW", df, PLAN, picks, 100_000.0)
    first, second, _ = run.segments
    assert first.trades[0].exit_date == df.index[621]
    assert first.trades[0].exit_reason == ExitReason.TIME
    assert (first.end, second.start) == (621, 621)
    assert [trade.signal_date for trade in second.trades] == [df.index[650]]  # 605 came before it could trade


def test_a_window_whose_bars_the_window_before_still_trades_is_skipped():
    df = random_walk(1000)
    run = stitch(VectorizedEngine(), "RW", df, PLAN, [_case((450,)), _case((650,), hold=400), _case((850,))], 100_000.0)
    second, third = run.segments[1:]
    assert second.trades[0].exit_reason == ExitReason.OPEN
    assert second.end == 999
    assert not third.traded
    assert third.trades == ()
    assert list(run.equity.index) == list(df.index[400:])


def test_a_window_without_a_pick_holds_cash():
    df = random_walk(1000)
    run = stitch(VectorizedEngine(), "RW", df, PLAN, [_case((450,)), None, _case((850,))], 100_000.0)
    second = run.segments[1]
    assert second.trades == ()
    assert (second.start, second.end) == (600, 800)
    assert (second.equity == run.segments[0].equity.iloc[-1]).all()


# --- The walk-forward use case -----------------------------------------------------------------------


@pytest.fixture
def frames():
    return {"AAA": random_walk(1500, seed=1), "TINY": random_walk(300, seed=2)}


def _use_cases(frames, runner=None):
    return build_use_cases(Settings(), FakeProvider(frames), runner=runner)


SETUP = BacktestRequest(ticker="aaa", signal="connors_rsi2_long", period="max")
AXES = (
    SweepAxis(SweepTarget.SIGNAL, "oversold", (5.0, 10.0, 15.0, 20.0)),
    SweepAxis(SweepTarget.EXIT, "target_r", (1.5, 2.5), owner="target"),
)


def _request(setup=SETUP, axes=AXES, **settings):
    return WalkForwardRequest(replace(setup, settings={"walk_forward": settings} if settings else {}), axes)


def test_each_window_trades_the_best_combination_of_its_in_sample_window(frames):
    report = _use_cases(frames).walk_forward.run(_request(min_trades=5))
    assert report.ticker == "AAA"
    assert len(report.windows) == 5
    assert len(report.combinations) == 8
    assert report.plan == plan_windows(1500, 5, 3.0, WindowScheme.ROLLING)

    # The pick of a window is the combination with the highest in-sample Sharpe, computed directly.
    window = report.windows[1]
    engine, df = VectorizedEngine(), frames["AAA"]
    direct = [in_sample_metrics(engine, "AAA", df, item.case, window.window.in_sample) for item in report.combinations]
    assert window.pick.combination == pick(direct, "sharpe", 5)
    assert window.pick.in_sample == direct[window.pick.combination]
    assert window.pick.qualified == sum(metrics.trades >= 5 for metrics in direct)

    # The stitched curve is each window's pick traded on its window, and the unchanged setup trades the same bars.
    picked = [report.combinations[item.pick.combination].case for item in report.windows]
    stitched = stitch(engine, "AAA", df, report.plan, picked, report.base.config.initial_equity)
    assert report.stitched.equity.equals(stitched.equity)
    assert report.metrics == compute_metrics(stitched.equity, stitched.trades, df["close"].iloc[report.plan.start :])
    unchanged = engine.run(
        "AAA", df, SignalFrom(report.base.signal, report.plan.start), report.base.config, report.base.rules
    )
    assert report.unchanged.trades == unchanged.trades
    assert report.unchanged_metrics.buy_hold_pct == report.metrics.buy_hold_pct
    assert report.next_pick.span == Span(1500 - 561, 1500)
    assert report.next_pick.combination is not None


def test_a_walk_forward_reads_its_windows_scheme_and_metric(frames):
    request = replace(
        _request(windows=3, in_sample_ratio=2, min_trades=0), scheme=WindowScheme.ANCHORED, metric="expectancy_r"
    )
    report = _use_cases(frames).walk_forward.run(request)
    assert report.plan == plan_windows(1500, 3, 2.0, WindowScheme.ANCHORED)
    assert report.metric == "expectancy_r"
    assert (report.settings.windows, report.settings.in_sample_ratio) == (3, 2.0)
    for window in report.windows:
        values = [
            in_sample_metrics(VectorizedEngine(), "AAA", frames["AAA"], item.case, window.window.in_sample).expectancy_r
            for item in report.combinations
        ]
        assert window.pick.in_sample.expectancy_r == max(value for value in values if not math.isnan(value))


def test_windows_where_no_combination_has_enough_trades_hold_cash(frames):
    report = _use_cases(frames).walk_forward.run(_request(min_trades=500))
    assert all(window.pick.combination is None and window.pick.qualified == 0 for window in report.windows)
    assert report.stitched.trades == ()
    assert (report.stitched.equity == report.base.config.initial_equity).all()
    assert math.isnan(report.efficiency)
    assert report.next_pick.combination is None


def test_later_bars_change_neither_earlier_picks_nor_the_curve_before_them(frames):
    df = frames["AAA"]
    plan = plan_windows(len(df), 5, 3.0, WindowScheme.ROLLING)
    cut = plan.windows[2].out_of_sample.start
    other = random_walk(1500, seed=9)
    changed = df.copy()
    scale = df["close"].iloc[cut - 1] / other["close"].iloc[cut - 1]
    changed.iloc[cut:, :4] = other.iloc[cut:, :4].to_numpy() * scale
    changed.iloc[cut:, 4] = other.iloc[cut:, 4].to_numpy()
    before = _use_cases(frames).walk_forward.run(_request(min_trades=5))
    after = _use_cases({"AAA": changed}).walk_forward.run(_request(min_trades=5))
    assert [window.pick for window in before.windows[:3]] == [window.pick for window in after.windows[:3]]
    assert before.stitched.equity.iloc[: cut - plan.start].equals(after.stitched.equity.iloc[: cut - plan.start])
    assert [window.pick for window in before.windows[3:]] != [window.pick for window in after.windows[3:]]


def test_a_combination_breaking_a_rule_between_parameters_is_never_picked(frames):
    setup = BacktestRequest(ticker="AAA", signal="golden_cross", params={"slow": 60}, period="max")
    axes = (SweepAxis(SweepTarget.SIGNAL, "fast", (20.0, 40.0, 80.0)),)
    report = _use_cases(frames).walk_forward.run(_request(setup, axes, min_trades=0))
    assert report.combinations[2].case is None
    assert "must be shorter" in report.combinations[2].error
    assert all(window.pick.combination != 2 for window in report.windows)


@pytest.mark.parametrize(
    ("axis", "message"),
    [
        (SweepAxis(SweepTarget.SETTINGS, "equity", (1e4, 2e4), owner="account"), "carried from window to window"),
        (SweepAxis(SweepTarget.SETTINGS, "oos_pct", (20, 30), owner="backtest"), "no effect in a walk-forward"),
        (SweepAxis(SweepTarget.SETTINGS, "windows", (3, 4), owner="walk_forward"), "account, risk, backtest"),
    ],
)
def test_a_walk_forward_cannot_sweep_what_its_windows_set(frames, axis, message):
    with pytest.raises(ValueError, match=message):
        _use_cases(frames).walk_forward.run(_request(axes=(axis,)))


def test_walk_forward_limits(frames, monkeypatch):
    with pytest.raises(ValueError, match="Unknown selection metric 'trades'"):
        _use_cases(frames).walk_forward.run(replace(_request(), metric="trades"))
    with pytest.raises(ValueError, match="TINY: 300 bars are too few for 5 windows"):
        _use_cases(frames).walk_forward.run(_request(replace(SETUP, ticker="TINY")))
    with pytest.raises(ValueError, match="windows must be between 2 and 20"):
        _use_cases(frames).walk_forward.run(_request(windows=1))
    monkeypatch.setattr(walk_forward_service, "MAX_RUNS", 40)
    with pytest.raises(
        ValueError, match=r"8 combinations on 6 in-sample windows .* 48 backtests; a walk-forward runs at most 40"
    ):
        _use_cases(frames).walk_forward.run(_request())


def test_walk_forward_on_worker_processes_matches_one_process(frames):
    one = _use_cases(frames).walk_forward.run(_request(min_trades=5))
    many = _use_cases(frames, ProcessRunner(workers=2, min_items=1)).walk_forward.run(_request(min_trades=5))
    assert [window.pick for window in many.windows] == [window.pick for window in one.windows]
    assert many.stitched.equity.equals(one.stitched.equity)
    assert isinstance(many.stitched.equity, pd.Series)
