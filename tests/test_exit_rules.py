"""Levels of the trailing, channel and breakeven stops, close by close, on hand-made bars."""

import math

import numpy as np
import pytest

from tradescan.backtest.exits import BreakevenStop, ChannelStop, ExitRule, OpenTrade, TrailingStop, exit_rules
from tradescan.backtest.rules import Bars
from tradescan.signals import Direction


def _array(values, length: int, fill: float) -> np.ndarray:
    return np.full(length, fill) if values is None else np.asarray(values, dtype=float)


def _bars(high=None, low=None, atr=None) -> Bars:
    """Only the arrays a rule reads matter; the others are filled with zeros, the ATR with ones."""
    length = len(high if high is not None else low)
    zeros = np.zeros(length)
    return Bars(
        open=zeros, high=_array(high, length, 0.0), low=_array(low, length, 0.0), close=zeros, atr=_array(atr, length, 1.0)
    )


def _stops(rule: ExitRule, bars: Bars, direction=Direction.LONG, entry_index=0, entry_price=100.0, reference=100.0, risk=4.0):
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
