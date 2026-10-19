import numpy as np
import pandas as pd
import pytest
from tests.synthetic import FakeProvider, random_walk

from tradescan.backtest.base import ExitReason, Trade
from tradescan.backtest.monte_carlo import METHODS, MonteCarloConfig, closed_r_multiples, simulate
from tradescan.config import Settings
from tradescan.services import BacktestRequest, build_use_cases
from tradescan.signals.base import Direction

R = np.array([2.0, -1.0, -1.0, 3.0, -1.0, 0.5, -1.0, -1.0, -1.0, 2.5] * 4)


def method(result, name):
    return next(distribution for distribution in result.methods if distribution.method.name == name)


def test_the_actual_order_is_traded_with_fixed_fractional_sizing():
    result = simulate(np.array([1.0, -1.0, -1.0, 2.0]), 10.0, MonteCarloConfig(simulations=100))
    assert result.trades == 4 and result.risk_pct == 10.0
    assert result.actual.final_return_pct == pytest.approx((1.1 * 0.9 * 0.9 * 1.2 - 1) * 100)
    assert result.actual.max_drawdown_pct == pytest.approx((0.9 * 0.9 - 1) * 100)
    assert result.actual.longest_losing_streak == 2
    assert [distribution.method.name for distribution in result.methods] == ["shuffled", "bootstrapped"]


def test_shuffling_keeps_the_final_return_and_spreads_the_drawdown():
    result = simulate(R, 1.0, MonteCarloConfig(simulations=500))
    shuffled = method(result, "shuffled")
    final = shuffled.final_return_pct
    assert final.p5 == pytest.approx(result.actual.final_return_pct) and final.p95 == pytest.approx(final.p5)
    drawdown = shuffled.max_drawdown_pct
    assert drawdown.p5 < drawdown.p25 < drawdown.p50 < drawdown.p75 < drawdown.p95 < 0
    streak = shuffled.longest_losing_streak
    assert 3 <= streak.p5 <= streak.p50 <= streak.p95 <= (R < 0).sum()


def test_bootstrapping_spreads_the_final_return():
    final = method(simulate(R, 1.0, MonteCarloConfig(simulations=500)), "bootstrapped").final_return_pct
    assert final.p5 < final.p50 < final.p95


def test_the_seed_repeats_the_simulations():
    first = simulate(R, 1.0, MonteCarloConfig(simulations=300, seed=7))
    assert simulate(R, 1.0, MonteCarloConfig(simulations=300, seed=7)) == first
    other = simulate(R, 1.0, MonteCarloConfig(simulations=300, seed=8))
    assert method(other, "bootstrapped").final_return_pct != method(first, "bootstrapped").final_return_pct


def test_batches_cover_every_simulation():
    # More simulations than one batch: the same seed gives the same first batch, so the medians stay close.
    small = method(simulate(R, 1.0, MonteCarloConfig(simulations=1000)), "bootstrapped")
    large = method(simulate(R, 1.0, MonteCarloConfig(simulations=2500)), "bootstrapped")
    assert large.final_return_pct.p50 == pytest.approx(small.final_return_pct.p50, abs=5.0)


def test_ruin_is_a_drawdown_at_least_as_deep_as_the_ruin_level():
    losers = np.full(10, -1.0)  # 0.9 ** 10 - 1 = -65% at 10% risk
    deep = simulate(losers, 10.0, MonteCarloConfig(simulations=100, ruin_drawdown_pct=60.0))
    assert all(distribution.ruin_pct == 100.0 for distribution in deep.methods)
    shallow = simulate(losers, 10.0, MonteCarloConfig(simulations=100, ruin_drawdown_pct=70.0))
    assert all(distribution.ruin_pct == 0.0 for distribution in shallow.methods)


def test_equity_stops_at_zero():
    result = simulate(np.array([-1.5, 3.0, 2.0]), 100.0, MonteCarloConfig(simulations=100, ruin_drawdown_pct=100.0))
    assert result.actual.final_return_pct == -100.0 and result.actual.max_drawdown_pct == -100.0
    assert method(result, "shuffled").ruin_pct == 100.0  # every order loses everything on the -1.5R trade


def test_too_few_trades_give_no_simulation():
    assert simulate(np.array([1.0]), 1.0, MonteCarloConfig()) is None
    assert simulate(np.array([]), 1.0, MonteCarloConfig()) is None


def trade(r_multiple, reason=ExitReason.TARGET):
    day = pd.Timestamp("2020-01-02")
    return Trade(Direction.LONG, day, day, day, 10.0, 11.0, 1.0, 1.0, r_multiple, reason)


def test_only_closed_trades_with_an_r_multiple_are_resampled():
    trades = [trade(1.0), trade(float("nan")), trade(-1.0), trade(2.0, ExitReason.OPEN)]
    assert closed_r_multiples(trades).tolist() == [1.0, -1.0]


def test_methods_have_names_and_labels():
    assert all(item.name and item.label and item.description for item in METHODS)


def test_backtest_simulates_every_engine_run_with_the_run_settings():
    use_cases = build_use_cases(Settings(), FakeProvider({"AAA": random_walk(1500, seed=1)}))
    settings = {"account": {"risk_pct": 2.0}, "monte_carlo": {"simulations": 200, "ruin_drawdown_pct": 30, "seed": 3}}
    report = use_cases.backtest.run(BacktestRequest(ticker="AAA", signal="connors_rsi2_long", settings=settings))
    run = report.runs[0]
    result = run.monte_carlo
    assert result is not None and result.trades == run.metrics.trades
    assert (result.config.simulations, result.config.ruin_drawdown_pct, result.config.seed) == (200, 30.0, 3)
    assert result.risk_pct == 2.0
    assert result == simulate(closed_r_multiples(run.result.trades), 2.0, result.config)
