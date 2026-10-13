import numpy as np
import pandas as pd
import pytest
from synthetic import make_ohlcv, random_walk

from tradescan.signals import Direction, Family, default_registry
from tradescan.signals.conditions import bars_since_last, crossed_above, rising_edge

ALL_SIGNALS = default_registry.names()
WALK = random_walk()


def test_registry_contains_paired_library():
    assert len(ALL_SIGNALS) == 30
    longs = default_registry.select(directions={Direction.LONG})
    assert {signal.direction for signal in longs} == {Direction.LONG}
    breakouts = default_registry.select(families={Family.BREAKOUT})
    assert {signal.family for signal in breakouts} == {Family.BREAKOUT}


def test_unknown_signal_has_helpful_error():
    with pytest.raises(KeyError, match="list-signals"):
        default_registry.create("nope")


@pytest.mark.parametrize("name", ALL_SIGNALS)
def test_events_are_boolean_and_aligned(name):
    events = default_registry.create(name).events(WALK)
    assert events.dtype == bool
    assert events.index.equals(WALK.index)


@pytest.mark.parametrize("name", ALL_SIGNALS)
def test_no_look_ahead(name):
    signal = default_registry.create(name)
    full = signal.events(WALK)
    for cut in (400, 1300, 2200):
        assert signal.events(WALK.iloc[:cut]).equals(full.iloc[:cut]), f"{name} changed past values at cut {cut}"


@pytest.mark.parametrize("name", ALL_SIGNALS)
def test_every_signal_fires_on_varied_data(name):
    assert default_registry.create(name).events(WALK).sum() > 0


@pytest.mark.parametrize("name", ALL_SIGNALS)
def test_events_never_fire_on_consecutive_bars(name):
    events = default_registry.create(name).events(WALK).to_numpy()
    assert not (events[1:] & events[:-1]).any()


def test_golden_cross_fires_once_after_the_turn():
    close = np.r_[np.linspace(200, 100, 300), np.linspace(100, 220, 300)]
    events = default_registry.create("golden_cross").events(make_ohlcv(close))
    assert events.sum() == 1
    assert np.flatnonzero(events.to_numpy())[0] > 300


def test_donchian_breakout_on_first_close_above_channel():
    close = [100.0] * 30 + [105.0, 106.0]
    events = default_registry.create("donchian_breakout").events(make_ohlcv(close, spread=0.0))
    assert np.flatnonzero(events.to_numpy()).tolist() == [30]


def test_gap_and_go_needs_gap_body_and_volume():
    close = [100.0] * 30 + [104.0]
    opens = [100.0] * 30 + [102.5]
    volume = [1_000.0] * 30 + [2_000.0]
    events = default_registry.create("gap_and_go_up").events(make_ohlcv(close, opens=opens, volume=volume))
    assert events.iloc[-1]
    quiet = default_registry.create("gap_and_go_up").events(make_ohlcv(close, opens=opens, volume=1_000.0))
    assert not quiet.iloc[-1]


def test_condition_helpers():
    series = pd.Series([1.0, 2.0, 3.0, 2.0, 4.0])
    assert crossed_above(series, 2.5).tolist() == [False, False, True, False, True]
    assert rising_edge(pd.Series([True, True, False, True])).tolist() == [True, False, False, True]
    events = pd.Series([False, True, False, False])
    assert bars_since_last(events, 3) == 2
    assert bars_since_last(events, 2) is None
