import math

import numpy as np
import pandas as pd
import pytest
from tests.synthetic import FixedSignal, make_ohlcv

from tradescan.backtest.edge import combine_samples, edge_samples, forward_returns
from tradescan.context import ContextBuilder, Trend
from tradescan.indicators import atr
from tradescan.regime import MarketRegimeAnalyzer, Regime
from tradescan.risk import RiskPlanner
from tradescan.scanner import Scanner, filter_hits, rs_percentiles
from tradescan.scoring import Scorer
from tradescan.signals import Direction, default_registry


def _breakout_frame():
    close = np.r_[np.linspace(100, 150, 300), np.full(25, 150.0), [160.0]]
    return make_ohlcv(close)


def _scanner(signals):
    return Scanner(
        signals=signals,
        context_builder=ContextBuilder(),
        scorer=Scorer({"breakout": 1.5}, {}),
        risk_planner=RiskPlanner(100_000, 1.0, 25.0, 2.0, (2.0, 3.0)),
        edge_horizon=5,
        fresh_bars=3,
        min_bars=60,
    )


def test_scanner_finds_scores_and_plans_a_fresh_breakout():
    frames = {"UP": _breakout_frame(), "NEW": make_ohlcv(np.linspace(10, 11, 30))}
    signals = default_registry.select(names=["donchian_breakout", "donchian_breakdown"])
    result = _scanner(signals).scan(frames)

    assert result.skipped == ["NEW"]
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert (hit.ticker, hit.direction) == ("UP", Direction.LONG)
    assert [(item.signal.name, item.bars_ago) for item in hit.fired] == [("donchian_breakout", 0)]
    assert hit.context.daily_trend is Trend.UP and hit.context.weekly_trend is Trend.UP
    assert hit.score.total == pytest.approx(1.5 + 1.0 + 1.0 + 1.0)
    expected_stop = 160.0 - 2.0 * atr(frames["UP"]).iloc[-1]
    assert hit.risk.stop == pytest.approx(expected_stop)
    assert hit.edge is not None and hit.edge.signal == "donchian_breakout"


def test_filter_hits_and_rs_percentiles():
    frames = {"UP": _breakout_frame()}
    hits = _scanner(default_registry.select(names=["donchian_breakout"])).scan(frames).hits
    assert filter_hits(hits, min_score=10.0) == []
    assert filter_hits(hits, directions={Direction.SHORT}) == []
    assert rs_percentiles({"A": 0.1, "B": 0.3, "C": math.nan}) == {"A": 50.0, "B": 100.0}


def test_regime_risk_on_and_risk_off():
    analyzer = MarketRegimeAnalyzer()
    up = {name: make_ohlcv(np.linspace(50, 100 + i, 300)) for i, name in enumerate("ABC")}
    on = analyzer.analyze("IDX", make_ohlcv(np.linspace(50, 100, 300)), up)
    assert on.regime is Regime.RISK_ON
    assert (on.pct_above_fast, on.new_highs, on.new_lows) == (100.0, 3, 0)

    down = {name: make_ohlcv(np.linspace(100 + i, 50, 300)) for i, name in enumerate("ABC")}
    off = analyzer.analyze("IDX", make_ohlcv(np.linspace(100, 50, 300)), down)
    assert off.regime is Regime.RISK_OFF and off.new_lows == 3
    assert analyzer.analyze("IDX", None, up).benchmark_above_slow is None


def test_forward_returns_enter_next_open_exit_close():
    df = make_ohlcv([10.0, 11.0, 12.0, 13.0], opens=[10.0, 10.5, 11.5, 12.5])
    returns = forward_returns(df, 2)
    assert returns.iloc[0] == pytest.approx(12.0 / 10.5 - 1)
    assert returns.iloc[2:].isna().all()


def _pooled(frames, signal, horizon):
    return combine_samples(signal.name, horizon, [edge_samples(df, signal, (horizon,))[0] for df in frames])


def test_edge_samples_pool_events_in_signal_direction():
    close = [10.0, 11.0, 12.0, 11.0, 10.0, 12.0, 13.0, 14.0]
    df = make_ohlcv(close)
    outcome = forward_returns(df, 1)
    long_stats = _pooled([df, df], FixedSignal(positions=(1, 3)), 1)
    assert long_stats.events == 4
    assert long_stats.mean_return == pytest.approx(outcome.iloc[[1, 3]].mean() * 100)
    assert long_stats.baseline_return == pytest.approx(outcome.dropna().mean() * 100)
    assert long_stats.edge == pytest.approx(long_stats.mean_return - long_stats.baseline_return)

    short_stats = _pooled([df], FixedSignal(positions=(1, 3), side=Direction.SHORT), 1)
    assert short_stats.mean_return == pytest.approx(-outcome.iloc[[1, 3]].mean() * 100)

    empty = _pooled([df], FixedSignal(positions=()), 1)
    assert empty.events == 0 and math.isnan(empty.win_rate)
    assert isinstance(empty.baseline_return, float) and not pd.isna(empty.baseline_return)
