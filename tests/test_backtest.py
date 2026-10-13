import numpy as np
import pandas as pd
import pytest
from synthetic import FixedSignal, random_walk

from tradescan.backtest.base import BacktestConfig, ExitReason
from tradescan.backtest.metrics import compute_metrics
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.signals import Direction, default_registry

NO_COSTS = BacktestConfig(risk_pct=1.0, max_position_pct=100.0, target_r=2.0, max_hold_bars=5, commission_pct=0.0, slippage_pct=0.0)


def _bars(overrides: dict[int, tuple[float, float, float, float]], length: int = 30) -> pd.DataFrame:
    """Flat bars (O=C=100, H=101, L=99, so ATR=2) with selected bars replaced by (open, high, low, close)."""
    rows = [overrides.get(i, (100.0, 101.0, 99.0, 100.0)) for i in range(length)]
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=pd.bdate_range("2020-01-01", periods=length))
    frame["volume"] = 1_000.0
    return frame


def _run(df, positions=(20,), side=Direction.LONG, config=NO_COSTS):
    return VectorizedEngine().run("TEST", df, FixedSignal(positions=positions, side=side), config)


def test_long_target_hit():
    # Signal on bar 20 (close 100, ATR 2): stop 96, target 108, size 1000/4 = 250.
    result = _run(_bars({22: (100.0, 109.0, 99.0, 105.0)}))
    (trade,) = result.trades
    assert (trade.exit_reason, trade.entry_price, trade.exit_price, trade.size) == (ExitReason.TARGET, 100.0, 108.0, 250)
    assert trade.pnl == pytest.approx(2_000.0) and trade.r_multiple == pytest.approx(2.0)
    assert result.equity.iloc[-1] == pytest.approx(102_000.0)
    assert result.equity.iloc[22] == pytest.approx(102_000.0)


def test_long_stop_gap_fills_at_open_and_stop_wins_same_bar_ties():
    gap = _run(_bars({22: (90.0, 91.0, 89.0, 90.0)})).trades[0]
    assert (gap.exit_reason, gap.exit_price) == (ExitReason.STOP, 90.0)
    assert gap.r_multiple == pytest.approx(-2.5)

    both = _run(_bars({22: (100.0, 110.0, 95.0, 100.0)})).trades[0]
    assert (both.exit_reason, both.exit_price) == (ExitReason.STOP, 96.0)


def test_entry_bar_range_is_not_checked_for_exits():
    trade = _run(_bars({21: (100.0, 101.0, 90.0, 100.0)})).trades[0]
    assert trade.exit_reason == ExitReason.TIME


def test_time_exit_at_open_after_max_hold_and_signals_ignored_while_in_trade():
    df = _bars({26: (102.0, 103.0, 101.0, 102.0)})
    result = _run(df, positions=(20, 22))
    (trade,) = result.trades
    assert trade.exit_reason == ExitReason.TIME
    assert trade.exit_date == df.index[26] and trade.exit_price == 102.0


def test_short_target_and_open_trade_at_end():
    df = _bars({22: (100.0, 101.0, 91.0, 95.0)})
    trade = _run(df, side=Direction.SHORT).trades[0]
    assert (trade.exit_reason, trade.exit_price) == (ExitReason.TARGET, 92.0)
    assert trade.pnl == pytest.approx(2_000.0)

    last = _run(_bars({}), positions=(27,)).trades[0]
    assert last.exit_reason == ExitReason.OPEN and not last.is_closed


def test_costs_reduce_pnl_and_equity_matches_trades():
    config = BacktestConfig(commission_pct=0.1, slippage_pct=0.05)
    df = random_walk(1500)
    result = VectorizedEngine().run("RW", df, default_registry.create("donchian_breakout"), config)
    assert len(result.trades) > 10
    closed = sum(trade.pnl for trade in result.trades)
    assert result.equity.iloc[-1] == pytest.approx(config.initial_equity + closed)
    for previous, current in zip(result.trades, result.trades[1:]):
        assert current.signal_date >= previous.exit_date


def test_metrics_on_known_values():
    equity = pd.Series([100.0, 110.0, 99.0, 120.0], index=pd.bdate_range("2020-01-01", periods=4))
    curve = compute_metrics(equity, [], equity, bars_per_year=252)
    assert curve.max_drawdown_pct == pytest.approx(-10.0)
    assert curve.total_return_pct == pytest.approx(20.0)
    assert curve.trades == 0 and np.isnan(curve.win_rate_pct)

    df = _bars({22: (100.0, 109.0, 99.0, 105.0)})
    result = _run(df)
    metrics = compute_metrics(result.equity, result.trades, df["close"], bars_per_year=252)
    assert metrics.trades == 1 and metrics.win_rate_pct == 100.0
    assert metrics.profit_factor == float("inf")
    assert metrics.expectancy_r == pytest.approx(2.0)
    assert metrics.exposure_pct == pytest.approx(100.0 / 30)


def test_cerebro_matches_vectorized_engine():
    pytest.importorskip("backtrader")
    from tradescan.backtest.cerebro import CerebroEngine

    df = random_walk(1500, seed=11)
    config = BacktestConfig(commission_pct=0.1, slippage_pct=0.05, max_hold_bars=15)
    for name in ("donchian_breakout", "ema_cross_down", "connors_rsi2_long", "gap_and_go_up", "supertrend_down"):
        signal = default_registry.create(name)
        fast = VectorizedEngine().run("RW", df, signal, config)
        slow = CerebroEngine().run("RW", df, signal, config)
        assert len(fast.trades) == len(slow.trades) > 0, name
        for left, right in zip(fast.trades, slow.trades):
            assert (left.entry_date, left.exit_date, left.exit_reason) == (right.entry_date, right.exit_date, right.exit_reason), name
            assert left.entry_price == pytest.approx(right.entry_price, rel=1e-9)
            assert left.exit_price == pytest.approx(right.exit_price, rel=1e-9)
            assert left.pnl == pytest.approx(right.pnl, rel=1e-6, abs=1e-6)
        np.testing.assert_allclose(fast.equity.to_numpy(), slow.equity.to_numpy(), rtol=1e-9)
