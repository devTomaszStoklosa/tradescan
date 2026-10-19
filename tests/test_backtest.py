import numpy as np
import pandas as pd
import pytest
from tests.synthetic import AdverseCloseExit, FixedSignal, RatchetStop, random_walk

from tradescan.backtest.base import BacktestConfig, ExitReason
from tradescan.backtest.entries import LimitEntry, NextOpenEntry, StopEntry, entry_rules
from tradescan.backtest.exits import (
    BreakevenStop,
    ChannelStop,
    FailedBreakoutExit,
    NoProgressExit,
    RsiExit,
    SmaRevertExit,
    SmaTrendExit,
    SupertrendExit,
    TargetExit,
    TimeExit,
    TrailingStop,
    exit_rules,
)
from tradescan.backtest.filters import AdxFilter, AtrPercentFilter, MarketFilter, TrendFilter, VolumeFilter
from tradescan.backtest.metrics import compute_metrics
from tradescan.backtest.rules import Bars
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


# --- Trailing, channel and breakeven stops -----------------------------------------------------------


def test_trailing_stop_exits_at_the_level_set_by_the_last_close(engine):
    # Entry at 100 on bar 21. The close of bar 23 trails the stop 1 ATR below its high of 111; bar 24 falls through it.
    df = _bars({22: (100.0, 106.0, 100.0, 105.0), 23: (105.0, 111.0, 105.0, 110.0), 24: (110.0, 110.5, 104.0, 105.0)})
    level = 111.0 - Bars.from_frame(df, NO_COSTS.atr_period).atr[23]
    (trade,) = _run(engine, df, rules=TradeRules(exits=(TrailingStop(atr_mult=1.0),))).trades
    assert (trade.exit_reason, trade.exit_date) == ("trailing", df.index[24])
    assert trade.exit_price == pytest.approx(level) and trade.r_multiple == pytest.approx((level - 100.0) / 4)

    # The breakeven stop (at 100 from bar 23 on) is looser, so the trailing stop still closes the trade.
    rules = TradeRules(exits=(BreakevenStop(), TrailingStop(atr_mult=1.0)))
    assert _run(engine, df, rules=rules).trades[0].exit_reason == "trailing"


def test_channel_stop_exits_below_the_lowest_low_of_the_last_bars(engine):
    # The 3-bar low rises from 99 to 99.5 (close of bar 24) and 100 (close of bar 25); bar 26 trades through 100.
    df = _bars(
        {
            22: (100.0, 103.0, 99.5, 102.0),
            23: (102.0, 104.0, 101.0, 103.0),
            24: (103.0, 105.0, 102.0, 104.0),
            25: (104.0, 104.5, 100.0, 100.5),
            26: (100.5, 101.0, 99.0, 99.5),
        }
    )
    (trade,) = _run(engine, df, rules=TradeRules(exits=(ChannelStop(period=3),))).trades
    assert (trade.exit_reason, trade.exit_date, trade.exit_price) == ("channel", df.index[26], 100.0)


def test_breakeven_stop_exits_at_the_fill_price(engine):
    # Fill 100, risk 4: bar 22's high of 105 passes the 1R trigger (104), so bar 23 stops out at 100.
    df = _bars({22: (100.0, 105.0, 100.5, 104.0), 23: (103.0, 103.5, 99.0, 99.5)})
    (trade,) = _run(engine, df, rules=TradeRules(exits=(BreakevenStop(),))).trades
    assert (trade.exit_reason, trade.exit_date, trade.exit_price) == ("breakeven", df.index[23], 100.0)
    assert trade.pnl == pytest.approx(0.0)


# --- Indicator exits -----------------------------------------------------------------------------------


def test_sma_revert_exit_leaves_at_the_open_after_a_close_above_the_average(engine):
    # The entry bar closes on its 3-bar average (100), so the trade stays; bar 22 closes above it (102 > 100.67).
    df = _bars({22: (100.0, 102.5, 99.5, 102.0), 23: (103.0, 103.5, 102.0, 103.0)})
    (trade,) = _run(engine, df, rules=TradeRules(exits=(SmaRevertExit(period=3),))).trades
    assert (trade.exit_reason, trade.exit_date, trade.exit_price) == ("sma_revert", df.index[23], 103.0)
    assert trade.r_multiple == pytest.approx(0.75)


def test_rsi_exit_closes_a_short_once_rsi_falls_to_the_mirrored_level(engine):
    # Flat bars keep RSI(2) at 50; bar 22's drop takes it to 0, at or below 100 - 70, so bar 23's open closes the short.
    df = _bars({22: (100.0, 100.5, 96.5, 97.0), 23: (96.0, 97.0, 95.5, 96.5)})
    (trade,) = _run(engine, df, side=Direction.SHORT, rules=TradeRules(exits=(RsiExit(period=2, level=70),))).trades
    assert (trade.exit_reason, trade.exit_date, trade.exit_price) == ("rsi", df.index[23], 96.0)
    assert trade.pnl == pytest.approx(1_000.0) and trade.r_multiple == pytest.approx(1.0)


# --- Breakout exits ------------------------------------------------------------------------------------


def test_failed_breakout_exit_leaves_at_the_open_after_a_close_back_below_the_reference(engine):
    # Reference 100 (the signal bar's close). Bar 22 closes 2 below it: more than 0.5 ATR, less than 1 ATR.
    df = _bars({22: (100.0, 100.5, 97.5, 98.0), 23: (98.5, 99.0, 97.5, 98.0)})
    atr = Bars.from_frame(df, NO_COSTS.atr_period).atr
    assert 0.5 * atr[22] < 2.0 < min(atr[22], atr[23])
    (trade,) = _run(engine, df, rules=TradeRules(exits=(FailedBreakoutExit(buffer_atr=0.5),))).trades
    assert (trade.exit_reason, trade.exit_date, trade.exit_price) == ("failed_breakout", df.index[23], 98.5)
    assert trade.r_multiple == pytest.approx(-0.375)

    # With a 1 ATR buffer, or with only the entry bar's close checked, the trade is still open on the last bar.
    for rule in (FailedBreakoutExit(buffer_atr=1.0), FailedBreakoutExit(buffer_atr=0.5, within_bars=1)):
        assert _run(engine, df, rules=TradeRules(exits=(rule,))).trades[0].exit_reason == ExitReason.OPEN


def test_no_progress_exit_closes_a_short_that_has_not_gained_enough(engine):
    # Fill 100, risk 4. The third close from the entry bar on (bar 23, 99) has gained 1: below 0.5R, exactly 0.25R.
    df = _bars({22: (100.0, 100.5, 98.0, 98.5), 23: (98.5, 99.5, 98.5, 99.0), 24: (99.5, 100.0, 99.0, 99.5)})
    rules = TradeRules(exits=(NoProgressExit(after_bars=3, min_r=0.5),))
    (trade,) = _run(engine, df, side=Direction.SHORT, rules=rules).trades
    assert (trade.exit_reason, trade.exit_date, trade.exit_price) == ("no_progress", df.index[24], 99.5)
    assert trade.pnl == pytest.approx(125.0) and trade.r_multiple == pytest.approx(0.125)

    rules = TradeRules(exits=(NoProgressExit(after_bars=3, min_r=0.25),))
    assert _run(engine, df, side=Direction.SHORT, rules=rules).trades[0].exit_reason == ExitReason.OPEN


def test_a_signal_a_filter_blocks_is_ignored_even_when_the_filter_allows_the_next_bars(engine):
    df = _bars({21: (100.0, 103.0, 99.0, 102.0), 22: (102.0, 104.0, 101.0, 103.0)})
    trend = TradeRules(exits=BRACKET.exits, filters=(TrendFilter(period=3),))
    assert len(_run(engine, df).trades) == 1
    assert _run(engine, df, rules=trend).trades == ()  # bar 20 closes at its SMA(3); bar 21 is no new signal
    assert [trade.signal_date for trade in _run(engine, df, positions=(20, 22), rules=trend).trades] == [df.index[22]]


def test_every_filter_has_to_allow_a_signal(engine):
    df = _bars({})  # flat bars: ATR is 2% of the close
    band = AtrPercentFilter(min_pct=1.0, max_pct=3.0)
    assert len(_run(engine, df, rules=TradeRules(exits=BRACKET.exits, filters=(band,))).trades) == 1
    both = TradeRules(exits=BRACKET.exits, filters=(band, VolumeFilter(min_ratio=2.0)))  # flat volume: a ratio of 1
    assert _run(engine, df, rules=both).trades == ()


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

# Every registered exit alone, none, combinations, and the test-only moving stop and exit at the open.
EXITS = [(cls(),) for cls in exit_rules.classes()] + [
    (),
    (TargetExit(target_r=1.5), TimeExit(max_hold_bars=12)),
    (TrailingStop(atr_mult=1.5), TargetExit(target_r=3.0)),
    (BreakevenStop(trigger_r=0.5, lock_r=0.1), ChannelStop(period=5), TimeExit(max_hold_bars=30)),
    (RsiExit(), TimeExit(max_hold_bars=10)),
    (SmaTrendExit(), TrailingStop(atr_mult=1.5)),
    (SupertrendExit(), SmaRevertExit(period=10), TargetExit(target_r=3.0)),
    (FailedBreakoutExit(), TrailingStop(atr_mult=1.5)),
    (NoProgressExit(after_bars=3, min_r=0.25), TargetExit(target_r=3.0)),
    (RatchetStop(),),
    (AdverseCloseExit(),),
    (RatchetStop(atr_mult=1.0), TargetExit(target_r=3.0), TimeExit(max_hold_bars=30)),
]

# Rules that must close some of the trades in the engine check whenever they are among its exits. Not the failed
# breakout exit: alone on `connors_rsi2_long`, only the stop is left to close its two trades, which last for years;
# the stop-entry check below asserts that it closes trades on both engines.
MUST_CLOSE = (
    TrailingStop, ChannelStop, BreakevenStop, RsiExit, SmaRevertExit, SmaTrendExit, SupertrendExit, NoProgressExit,
)  # fmt: skip

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
    for rule in exits:
        if isinstance(rule, MUST_CLOSE):
            assert rule.name in reasons


def test_engines_match_for_breakout_exits_after_a_stop_entry():
    # With a stop entry the reference is the order level above the signal bar's high (below its low for shorts).
    df = random_walk(1000, seed=23)
    rules = TradeRules(StopEntry(offset_atr=0.3, valid_bars=3), (FailedBreakoutExit(), NoProgressExit(), TrailingStop()))
    for name in ("donchian_breakout", "donchian_breakdown"):
        result = _assert_engines_match(df, default_registry.create(name), ENGINE_CHECK_CONFIG, rules)
        assert {"failed_breakout", "no_progress"} <= {trade.exit_reason for trade in result.trades}, name


# Every registered filter alone with its defaults, and combinations with other parameters.
FILTERS = [(cls(),) for cls in [TrendFilter, MarketFilter, AdxFilter, VolumeFilter, AtrPercentFilter]] + [
    (TrendFilter(period=50), AdxFilter(min_adx=20)),
    (VolumeFilter(period=10, min_ratio=1.2), MarketFilter(period=100)),
    (AtrPercentFilter(min_pct=1.5, max_pct=3.0), TrendFilter(period=100)),
]


@pytest.mark.parametrize("filters", FILTERS, ids=lambda filters: "+".join(rule.name for rule in filters))
@pytest.mark.parametrize("signal_name", ["donchian_breakout", "ema_cross_down"])
def test_engines_match_with_entry_filters(filters, signal_name):
    df = random_walk(1000, seed=24)
    benchmark = random_walk(1100, seed=25)["close"]  # starts on the same day and ends later
    signal = default_registry.create(signal_name)
    rules = TradeRules(filters=filters).with_benchmark(benchmark)
    result = _assert_engines_match(df, signal, ENGINE_CHECK_CONFIG, rules)
    allowed = rules.prepare(Bars.from_frame(df, ENGINE_CHECK_CONFIG.atr_period), signal.direction).allowed
    assert not allowed[signal.events(df).to_numpy()].all(), "the filters should block some signals"
    assert all(allowed[df.index.get_loc(trade.signal_date)] for trade in result.trades)
