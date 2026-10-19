"""Levels of the trailing, channel and breakeven stops and the indicator and breakout exits, close by close, on
hand-made bars."""

import math

import numpy as np
import pandas as pd
import pytest
from tests.synthetic import random_walk

from tradescan.backtest.exits import (
    BreakevenStop,
    ChannelStop,
    ExitRule,
    FailedBreakoutExit,
    NoProgressExit,
    OpenTrade,
    RsiExit,
    SmaRevertExit,
    SmaTrendExit,
    SupertrendExit,
    TrailingStop,
    exit_rules,
)
from tradescan.backtest.rules import Bars
from tradescan.indicators import supertrend
from tradescan.signals import Direction


def _array(values, length: int, fill: float) -> np.ndarray:
    return np.full(length, fill) if values is None else np.asarray(values, dtype=float)


def _bars(high=None, low=None, atr=None, close=None) -> Bars:
    """Only the arrays a rule reads matter; the others are filled with zeros, the ATR with ones."""
    length = len(next(values for values in (high, low, close) if values is not None))
    return Bars(
        open=np.zeros(length),
        high=_array(high, length, 0.0),
        low=_array(low, length, 0.0),
        close=_array(close, length, 0.0),
        volume=np.zeros(length),
        atr=_array(atr, length, 1.0),
        dates=pd.date_range("2024-01-01", periods=length, freq="B"),
    )


def _stops(
    rule: ExitRule, bars: Bars, direction=Direction.LONG, entry_index=0, entry_price=100.0, reference=100.0, risk=4.0
):
    """The stop the rule asks for at every close from the entry bar on (None for no stop)."""
    trade = OpenTrade(direction, entry_index, entry_price, reference, reference - direction.sign * risk, risk)
    tracker = rule.prepare(bars, direction)(trade)
    orders = [tracker.orders(index) for index in range(entry_index, len(bars))]
    assert all(order.stop is None or order.stop_reason == rule.name for order in orders)
    assert all(order.target is None and order.at_open is None for order in orders)
    return [order.stop for order in orders]


def test_trailing_stop_follows_the_best_price_since_entry_and_only_tightens():
    # Bar 0 is before the entry, so its high does not count; on bar 3 a wider ATR would loosen the stop.
    atr = [1, 1, 1, 3, 1]
    long = _bars(high=[50, 10, 12, 11, 15], atr=atr)
    assert _stops(TrailingStop(atr_mult=2), long, entry_index=1) == [8, 10, 10, 13]
    short = _bars(low=[1, 10, 8, 9, 5], atr=atr)
    assert _stops(TrailingStop(atr_mult=2), short, Direction.SHORT, entry_index=1) == [12, 10, 10, 7]


def test_trailing_stop_waits_for_a_finite_atr():
    assert _stops(TrailingStop(atr_mult=2), _bars(high=[10, 11], atr=[math.nan, 1])) == [None, 9]


def test_channel_stop_includes_bars_before_the_entry_and_only_tightens():
    # Rolling 3-bar low: 5, 3, 3, 3, 4, 2. From the entry on bar 2: 3, 3, 4 and then 4 again, as 2 would loosen it.
    assert _stops(ChannelStop(period=3), _bars(low=[5, 3, 4, 6, 7, 2]), entry_index=2) == [3, 3, 4, 4]
    short = _bars(high=[5, 7, 6, 4, 3, 8])
    assert _stops(ChannelStop(period=3), short, Direction.SHORT, entry_index=2) == [7, 7, 6, 6]


def test_breakeven_stop_moves_once_the_trigger_is_reached_and_stays():
    # Fill 100, risk 4: the 1R trigger is 104 and 0.5R locks in 102. The reference (99) is not used.
    rule = BreakevenStop(trigger_r=1, lock_r=0.5)
    long = _bars(high=[101, 103.9, 104, 101])
    assert _stops(rule, long, reference=99.0) == [None, None, 102, 102]
    assert _stops(BreakevenStop(), long, reference=99.0) == [None, None, 100, 100]
    short = _bars(low=[99, 96.1, 96, 99])
    assert _stops(rule, short, Direction.SHORT, reference=101.0) == [None, None, 98, 98]


def test_breakeven_lock_must_be_below_the_trigger():
    with pytest.raises(ValueError, match="must be below the trigger"):
        exit_rules.create("breakeven", {"lock_r": 1})
    assert exit_rules.create("breakeven", {"trigger_r": 2, "lock_r": 1.5}).lock_r == 1.5


def _exits(
    rule: ExitRule, bars: Bars, direction=Direction.LONG, entry_index=0, entry_price=100.0, reference=100.0, risk=4.0
) -> list[bool]:
    """Whether the rule asks to exit at the next open, at every close from the entry bar on."""
    trade = OpenTrade(direction, entry_index, entry_price, reference, reference - direction.sign * risk, risk)
    tracker = rule.prepare(bars, direction)(trade)
    orders = [tracker.orders(index) for index in range(entry_index, len(bars))]
    assert all(order.stop is None and order.target is None for order in orders)
    assert all(order.at_open in (None, rule.name) for order in orders)
    return [order.at_open is not None for order in orders]


def test_rsi_exit_mirrors_its_level_for_shorts():
    # RSI(2) of these closes: NaN, NaN, 0, 50, 87.5, 58.3.
    bars = _bars(close=[10, 9, 8, 9, 12, 11])
    assert _exits(RsiExit(period=2, level=70), bars) == [False, False, False, False, True, False]
    assert _exits(RsiExit(period=2, level=70), bars, Direction.SHORT) == [False, False, True, False, False, False]
    # The level itself exits, on both sides.
    assert _exits(RsiExit(period=2, level=50), bars) == [False, False, False, True, True, True]
    assert _exits(RsiExit(period=2, level=50), bars, Direction.SHORT) == [False, False, True, True, False, False]


def test_sma_exits_need_the_close_strictly_beyond_the_average():
    # SMA(3) of these closes: NaN, NaN, 11, 10.67, 11. Bar 2 closes on the average, so nothing exits there.
    bars = _bars(close=[10, 12, 11, 9, 13])
    assert _exits(SmaRevertExit(period=3), bars) == [False, False, False, False, True]
    assert _exits(SmaRevertExit(period=3), bars, Direction.SHORT) == [False, False, False, True, False]
    assert _exits(SmaTrendExit(period=3), bars) == [False, False, False, True, False]
    assert _exits(SmaTrendExit(period=3), bars, Direction.SHORT) == [False, False, False, False, True]
    assert _exits(SmaTrendExit(period=3), bars, entry_index=3) == [True, False]


def test_supertrend_exit_follows_the_direction_against_the_trade():
    df = random_walk(400, seed=5)
    bars = Bars.from_frame(df, 14)
    direction = supertrend(df, 10, 3.0)["direction"].to_numpy()
    long, short = (np.array(_exits(SupertrendExit(), bars, side)) for side in (Direction.LONG, Direction.SHORT))
    np.testing.assert_array_equal(long, direction == -1)
    np.testing.assert_array_equal(short, direction == 1)
    assert long.any() and short.any() and not (long | short)[np.isnan(direction)].any()


def test_failed_breakout_exit_checks_the_first_closes_against_the_reference():
    # Reference 100 (the fill, 97, is not used), ATR 2: a 0.5 ATR buffer needs a close below 99. Only the first
    # three closes count, the entry bar's included, so the closes of bars 4 and 5 never exit.
    rule = FailedBreakoutExit(buffer_atr=0.5, within_bars=3)
    long = _bars(close=[90, 100, 99, 98.9, 97, 95], atr=[2] * 6)
    assert _exits(rule, long, entry_index=1, entry_price=97.0) == [False, False, True, False, False]
    short = _bars(close=[110, 100, 101, 101.1, 103, 105], atr=[2] * 6)
    assert _exits(rule, short, Direction.SHORT, entry_index=1, entry_price=103.0) == [False, False, True, False, False]
    # Without a buffer any close below the reference exits, but not one on it.
    bare = FailedBreakoutExit(buffer_atr=0.0, within_bars=3)
    assert _exits(bare, long, entry_index=1) == [False, True, True, False, False]
    assert _exits(FailedBreakoutExit(buffer_atr=0.0, within_bars=1), long, entry_index=2) == [True, False, False, False]
    # Bars without an ATR never exit.
    assert not any(_exits(bare, _bars(close=[90, 100, 99, 98.9, 97, 95], atr=[math.nan] * 6), entry_index=1))


def test_no_progress_exit_checks_one_close_against_the_gain_from_the_fill():
    # Fill 100 (the reference, 99, is not used), risk 4. The third close from the entry on (bar 3) has gained 1,
    # which is below 0.5R (2) but not below 0.25R (1).
    long = _bars(close=[90, 100, 102, 101, 103])
    assert _exits(NoProgressExit(after_bars=3, min_r=0.5), long, entry_index=1, reference=99.0) == [
        False,
        False,
        True,
        False,
    ]
    assert not any(_exits(NoProgressExit(after_bars=3, min_r=0.25), long, entry_index=1, reference=99.0))
    short = _bars(close=[110, 100, 98, 99, 97])
    assert _exits(NoProgressExit(after_bars=3, min_r=0.5), short, Direction.SHORT, entry_index=1, reference=101.0) == [
        False,
        False,
        True,
        False,
    ]
    # One bar means the entry bar's close; a later close with enough gain keeps the trade.
    assert _exits(NoProgressExit(after_bars=1, min_r=0.5), long, entry_index=1) == [True, False, False, False]
    assert not any(_exits(NoProgressExit(after_bars=4, min_r=0.5), long, entry_index=1))
