import numpy as np
import pandas as pd
import pytest
from synthetic import AdverseCloseExit, FixedSignal, RatchetStop, random_walk

from tradescan.backtest.base import BacktestConfig, ExitReason
from tradescan.backtest.entries import LimitEntry, NextOpenEntry, StopEntry, entry_rules
from tradescan.backtest.exits import TargetExit, TimeExit, exit_rules
from tradescan.backtest.metrics import compute_metrics
from tradescan.backtest.trade_rules import TradeRules
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.signals import Direction, default_registry

NO_COSTS = BacktestConfig(risk_pct=1.0, max_position_pct=100.0, commission_pct=0.0, slippage_pct=0.0)
BRACKET = TradeRules(exits=(TargetExit(target_r=2.0), TimeExit(max_hold_bars=5)))


def _cerebro():
    pytest.importorskip("backtrader")
    from tradescan.backtest.cerebro import CerebroEngine

    return CerebroEngine()


@pytest.fixture(params=["vectorized", "cerebro"])
def engine(request):
    """Known-bar cases run on both engines, so the rules mean the same in each."""
    return VectorizedEngine() if request.param == "vectorized" else _cerebro()


def _bars(overrides: dict[int, tuple[float, float, float, float]], length: int = 30) -> pd.DataFrame:
    """Flat bars (O=C=100, H=101, L=99, so ATR=2) with selected bars replaced by (open, high, low, close)."""
    rows = [overrides.get(i, (100.0, 101.0, 99.0, 100.0)) for i in range(length)]
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=pd.bdate_range("2020-01-01", periods=length))
    frame["volume"] = 1_000.0
    return frame


def _run(engine, df, positions=(20,), side=Direction.LONG, config=NO_COSTS, rules=BRACKET):
    return engine.run("TEST", df, FixedSignal(positions=positions, side=side), config, rules)


# --- Next-open entry with target and time exit (the original rules) ---------------------------------


def test_long_target_hit(engine):
    # Signal on bar 20 (close 100, ATR 2): stop 96, target 108, size 1000/4 = 250.
    result = _run(engine, _bars({22: (100.0, 109.0, 99.0, 105.0)}))
    (trade,) = result.trades
    assert (trade.exit_reason, trade.entry_price, trade.exit_price, trade.size) == (ExitReason.TARGET, 100.0, 108.0, 250)
    assert trade.pnl == pytest.approx(2_000.0) and trade.r_multiple == pytest.approx(2.0)
    assert result.equity.iloc[-1] == pytest.approx(102_000.0)
    assert result.equity.iloc[22] == pytest.approx(102_000.0)


def test_long_stop_gap_fills_at_open_and_stop_wins_same_bar_ties(engine):
    gap = _run(engine, _bars({22: (90.0, 91.0, 89.0, 90.0)})).trades[0]
    assert (gap.exit_reason, gap.exit_price) == (ExitReason.STOP, 90.0)
    assert gap.r_multiple == pytest.approx(-2.5)

    both = _run(engine, _bars({22: (100.0, 110.0, 95.0, 100.0)})).trades[0]
    assert (both.exit_reason, both.exit_price) == (ExitReason.STOP, 96.0)


def test_stop_wins_even_when_the_bar_opens_beyond_the_target(engine):
    # Opens above the 108 target, then trades below the 96 stop: the stop order is checked first.
    trade = _run(engine, _bars({22: (110.0, 111.0, 95.0, 100.0)})).trades[0]
    assert (trade.exit_reason, trade.exit_price) == (ExitReason.STOP, 96.0)


def test_entry_bar_range_is_not_checked_for_exits(engine):
    trade = _run(engine, _bars({21: (100.0, 101.0, 90.0, 100.0)})).trades[0]
    assert trade.exit_reason == ExitReason.TIME


def test_time_exit_at_open_after_max_hold_and_signals_ignored_while_in_trade(engine):
    df = _bars({26: (102.0, 103.0, 101.0, 102.0)})
    result = _run(engine, df, positions=(20, 22))
    (trade,) = result.trades
    assert trade.exit_reason == ExitReason.TIME
    assert trade.exit_date == df.index[26] and trade.exit_price == 102.0


def test_short_target_and_open_trade_at_end(engine):
    df = _bars({22: (100.0, 101.0, 91.0, 95.0)})
    trade = _run(engine, df, side=Direction.SHORT).trades[0]
    assert (trade.exit_reason, trade.exit_price) == (ExitReason.TARGET, 92.0)
    assert trade.pnl == pytest.approx(2_000.0)

    last = _run(engine, _bars({}), positions=(27,)).trades[0]
    assert last.exit_reason == ExitReason.OPEN and not last.is_closed


def test_without_target_and_time_exit_only_the_stop_closes_the_trade(engine):
    df = _bars({22: (100.0, 120.0, 99.0, 110.0), 27: (100.0, 101.0, 95.0, 96.0)})
    (trade,) = _run(engine, df, rules=TradeRules(exits=())).trades
    assert (trade.exit_reason, trade.exit_date, trade.exit_price) == (ExitReason.STOP, df.index[27], 96.0)
    (held,) = _run(engine, _bars({}), rules=TradeRules(exits=())).trades
    assert held.exit_reason == ExitReason.OPEN


# --- Stop and limit entries --------------------------------------------------------------------------


def test_stop_entry_fills_at_its_level_or_at_a_gap_open(engine):
    # Buy-stop 0.5 ATR above the signal bar's high: 101 + 1 = 102. Stop and target come from 102.
    rules = TradeRules(entry=StopEntry(offset_atr=0.5), exits=(TargetExit(),))
    touched = _run(engine, _bars({21: (100.0, 103.0, 99.0, 102.5), 23: (104.0, 111.0, 103.0, 110.0)}), rules=rules).trades[0]
    assert (touched.entry_price, touched.exit_reason, touched.exit_price) == (102.0, ExitReason.TARGET, 110.0)
    assert touched.size == 250 and touched.r_multiple == pytest.approx(2.0)

    df = _bars({21: (105.0, 106.0, 104.0, 105.0)})
    gapped = _run(engine, df, rules=rules).trades[0]
    assert (gapped.entry_date, gapped.entry_price) == (df.index[21], 105.0)

    assert not _run(engine, _bars({}), rules=rules).trades  # the high never reaches 102


def test_short_stop_entry_sells_below_the_signal_bars_low(engine):
    rules = TradeRules(entry=StopEntry(offset_atr=0.5), exits=(TargetExit(),))
    trade = _run(engine, _bars({21: (100.0, 100.5, 97.0, 97.5)}), side=Direction.SHORT, rules=rules).trades[0]
    assert trade.entry_price == 98.0 and trade.direction is Direction.SHORT


def test_limit_entry_fills_at_its_level_or_better(engine):
    # Buy-limit 0.5 ATR below the signal close: 100 - 1 = 99, so the stop is 95 and the target 107.
    rules = TradeRules(entry=LimitEntry(offset_atr=0.5), exits=(TargetExit(),))
    touched = _run(engine, _bars({22: (100.0, 108.0, 99.0, 104.0)}), rules=rules).trades[0]
    assert (touched.entry_price, touched.exit_reason, touched.exit_price) == (99.0, ExitReason.TARGET, 107.0)

    gapped = _run(engine, _bars({21: (97.0, 98.0, 96.5, 97.5)}), rules=rules).trades[0]
    assert gapped.entry_price == 97.0

    assert not _run(engine, _bars({21: (100.0, 101.0, 99.5, 100.0)}), rules=TradeRules(entry=LimitEntry(offset_atr=0.5))).trades


def test_unfilled_orders_expire_and_signals_wait_for_them(engine):
    # The 99 buy-limit is out of reach on bars 21 and 22 and reachable from bar 23 on.
    df = _bars({21: (100.0, 101.0, 99.5, 100.0), 22: (100.0, 101.0, 99.5, 100.0)})
    patient = _run(engine, df, positions=(20, 22), rules=TradeRules(entry=LimitEntry(valid_bars=3))).trades
    assert [(t.signal_date, t.entry_date) for t in patient] == [(df.index[20], df.index[23])]

    # Active on bars 21 and 22 only: it expires at the close of bar 22, where a new signal places a new order.
    renewed = _run(engine, df, positions=(20, 22), rules=TradeRules(entry=LimitEntry(valid_bars=2))).trades
    assert [(t.signal_date, t.entry_date) for t in renewed] == [(df.index[22], df.index[23])]


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
    result = _run(VectorizedEngine(), df)
    metrics = compute_metrics(result.equity, result.trades, df["close"], bars_per_year=252)
    assert metrics.trades == 1 and metrics.win_rate_pct == 100.0
    assert metrics.profit_factor == float("inf")
    assert metrics.expectancy_r == pytest.approx(2.0)
    assert metrics.exposure_pct == pytest.approx(100.0 / 30)


def test_rules_reject_repeated_exits():
    with pytest.raises(ValueError, match="more than once: time"):
        TradeRules(exits=(TimeExit(), TargetExit(), TimeExit(max_hold_bars=3)))


# --- Both engines give identical trades for every rule ----------------------------------------------


def _assert_engines_match(df, signal, config, rules=None):
    fast = VectorizedEngine().run("RW", df, signal, config, rules)
    slow = _cerebro().run("RW", df, signal, config, rules)
    assert len(fast.trades) == len(slow.trades) > 0, signal
    for left, right in zip(fast.trades, slow.trades):
        assert (left.entry_date, left.exit_date, left.exit_reason) == (right.entry_date, right.exit_date, right.exit_reason), signal
        assert left.entry_price == pytest.approx(right.entry_price, rel=1e-9)
        assert left.exit_price == pytest.approx(right.exit_price, rel=1e-9)
        assert left.pnl == pytest.approx(right.pnl, rel=1e-6, abs=1e-6)
    np.testing.assert_allclose(fast.equity.to_numpy(), slow.equity.to_numpy(), rtol=1e-9)
    return fast


def test_cerebro_matches_vectorized_engine():
    df = random_walk(1500, seed=11)
    config = BacktestConfig(commission_pct=0.1, slippage_pct=0.05)
    rules = TradeRules(exits=(TargetExit(), TimeExit(max_hold_bars=15)))
    for name in ("donchian_breakout", "ema_cross_down", "connors_rsi2_long", "gap_and_go_up", "supertrend_down"):
        _assert_engines_match(df, default_registry.create(name), config, rules)


def test_engines_match_with_non_default_parameters():
    df = random_walk(1500, seed=12)
    config = BacktestConfig(
        risk_pct=2.0, max_position_pct=50.0, atr_period=20, atr_mult=3.0, commission_pct=0.2, slippage_pct=0.1,
    )  # fmt: skip
    rules = TradeRules(exits=(TargetExit(target_r=1.5), TimeExit(max_hold_bars=8)))
    for name, params in (
        ("donchian_breakout", {"period": 35}),
        ("connors_rsi2_long", {"rsi_period": 3, "oversold": 20, "trend_period": 100}),
        ("macd_cross_down", {"fast": 8, "slow": 30, "signal": 5}),
    ):
        _assert_engines_match(df, default_registry.create(name, params), config, rules)


ENTRIES = [cls() for cls in entry_rules.classes()] + [StopEntry(offset_atr=0.3, valid_bars=3), LimitEntry(offset_atr=0.2, valid_bars=4)]

# Every registered exit alone, none, and the test-only moving stop and exit at the open (what T1 and M2 need).
EXITS = [(cls(),) for cls in exit_rules.classes()] + [
    (),
    (TargetExit(target_r=1.5), TimeExit(max_hold_bars=12)),
    (RatchetStop(),),
    (AdverseCloseExit(),),
    (RatchetStop(atr_mult=1.0), TargetExit(target_r=3.0), TimeExit(max_hold_bars=30)),
]

ENGINE_CHECK_CONFIG = BacktestConfig(commission_pct=0.1, slippage_pct=0.05)


@pytest.mark.parametrize("entry", ENTRIES, ids=repr)
@pytest.mark.parametrize("signal_name", ["donchian_breakout", "ema_cross_down"])
def test_engines_match_for_every_entry_rule(entry, signal_name):
    df = random_walk(1000, seed=21)
    _assert_engines_match(df, default_registry.create(signal_name), ENGINE_CHECK_CONFIG, TradeRules(entry=entry))


@pytest.mark.parametrize("exits", EXITS, ids=lambda rules: "+".join(rule.name for rule in rules) or "stop_only")
@pytest.mark.parametrize("entry", [NextOpenEntry(), LimitEntry(valid_bars=2)], ids=["next_open", "limit"])
@pytest.mark.parametrize("signal_name", ["connors_rsi2_long", "ema_cross_down"])
def test_engines_match_for_every_exit_rule(exits, entry, signal_name):
    df = random_walk(1000, seed=22)
    result = _assert_engines_match(df, default_registry.create(signal_name), ENGINE_CHECK_CONFIG, TradeRules(entry, exits))
    reasons = {trade.exit_reason for trade in result.trades}
    if any(isinstance(rule, RatchetStop) for rule in exits):
        assert "trailing" in reasons
    if any(isinstance(rule, AdverseCloseExit) for rule in exits):
        assert "signal" in reasons
