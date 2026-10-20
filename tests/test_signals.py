import numpy as np
import pandas as pd
import pytest

from tests.synthetic import make_ohlcv, random_walk
from tradescan.signals import Direction, Family, default_registry
from tradescan.signals.conditions import bars_since_last, crossed_above, rising_edge

ALL_SIGNALS = default_registry.names()
WALK = random_walk()


def test_registry_contains_paired_library():
    assert len(ALL_SIGNALS) == 38
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


def test_ibs_fires_on_a_close_at_the_edge_of_the_range():
    # IBS: 0.5, 0.1, 0.05, 0.85, 0.0, 0.5, then a bar without range.
    close = [11.0, 10.2, 10.1, 11.7, 10.0, 11.0, 10.0]
    high = [12.0] * 6 + [10.0]
    df = pd.DataFrame(
        {"open": 11.0, "high": high, "low": 10.0, "close": close, "volume": 1.0},
        index=pd.bdate_range("2020-01-01", periods=len(close)),
    )
    assert np.flatnonzero(default_registry.create("ibs_low").events(df).to_numpy()).tolist() == [1, 4]
    assert np.flatnonzero(default_registry.create("ibs_high").events(df).to_numpy()).tolist() == [3]
    assert np.flatnonzero(default_registry.create("ibs_low", {"zone": 0.03}).events(df).to_numpy()).tolist() == [4]


def test_streak_fires_once_on_the_nth_close_in_a_row():
    df = make_ohlcv([10.0, 9.0, 8.0, 7.0, 6.0, 7.0, 6.0, 5.0, 4.0])
    assert np.flatnonzero(default_registry.create("down_streak").events(df).to_numpy()).tolist() == [3, 8]
    assert np.flatnonzero(default_registry.create("down_streak", {"bars": 4}).events(df).to_numpy()).tolist() == [4]
    assert not default_registry.create("up_streak").events(df).any()


def test_cumulative_rsi_fires_when_the_summed_rsi_drops_below_the_level():
    close = [*list(np.linspace(100.0, 130.0, 31)), 125.0, 120.0]
    events = default_registry.create("cumulative_rsi_long").events(make_ohlcv(close))
    # RSI(2) is 100 on the rise, then about 17 and 6: only the second drop takes the sum below 35.
    assert np.flatnonzero(events.to_numpy()).tolist() == [32]


@pytest.mark.parametrize(
    ("name", "params"),
    [("cumulative_rsi_long", {"oversold": 200}), ("cumulative_rsi_short", {"overbought": 250})],
)
def test_cumulative_rsi_level_must_be_reachable(name, params):
    with pytest.raises(ValueError, match="must be below 200"):
        default_registry.create(name, params)
    assert default_registry.create(name, {**params, "bars": 3}).bars == 3


def test_percent_b_fires_beyond_the_bands_but_not_without_width():
    df = make_ohlcv([100.0, 101.0] * 15 + [95.0])
    assert np.flatnonzero(default_registry.create("bb_pctb_low").events(df).to_numpy()).tolist() == [30]
    flat = make_ohlcv([100.0] * 40)
    assert not default_registry.create("bb_pctb_low").events(flat).any()
    assert not default_registry.create("bb_pctb_high").events(flat).any()


def test_condition_helpers():
    series = pd.Series([1.0, 2.0, 3.0, 2.0, 4.0])
    assert crossed_above(series, 2.5).tolist() == [False, False, True, False, True]
    assert rising_edge(pd.Series([True, True, False, True])).tolist() == [True, False, False, True]
    events = pd.Series([False, True, False, False])
    assert bars_since_last(events, 3) == 2
    assert bars_since_last(events, 2) is None
