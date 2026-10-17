from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from synthetic import FixedSignal, RatchetStop, random_walk

from tradescan.backtest.base import BacktestConfig, ExitReason, Fill
from tradescan.backtest.entries import LimitEntry, StopEntry
from tradescan.backtest.exits import BreakevenStop, OpenTrade, TargetExit, TimeExit, TrailingStop
from tradescan.backtest.pyramid import Pyramiding
from tradescan.backtest.trade_rules import TradeRules
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.report.tables import trades_to_frame
from tradescan.signals import Direction, default_registry

# 1% risk at a 2 ATR stop: 250 shares per unit on the flat bars below (ATR 2, stop 4 away). Units 1 ATR (2) apart.
NO_COSTS = BacktestConfig(max_position_pct=100.0, commission_pct=0.0, slippage_pct=0.0, max_units=3, add_every_atr=1.0)
STOP_ONLY = TradeRules(exits=())


def _cerebro():
    pytest.importorskip("backtrader")
    from tradescan.backtest.cerebro import CerebroEngine

    return CerebroEngine()


@pytest.fixture(params=["vectorized", "cerebro"])
def engine(request):
    return VectorizedEngine() if request.param == "vectorized" else _cerebro()


def _bars(overrides: dict[int, tuple[float, float, float, float]], length: int = 30) -> pd.DataFrame:
    """Flat bars (O=C=100, H=101, L=99, so ATR=2) with selected bars replaced by (open, high, low, close)."""
    rows = [overrides.get(i, (100.0, 101.0, 99.0, 100.0)) for i in range(length)]
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=pd.bdate_range("2020-01-01", periods=length))
    frame["volume"] = 1_000.0
    return frame


def _run(engine, df, side=Direction.LONG, config=NO_COSTS, rules=STOP_ONLY):
    """A signal at the close of bar 20 (close 100, ATR 2), filled at the open of bar 21."""
    return engine.run("TEST", df, FixedSignal(positions=(20,), side=side), config, rules)


RISING = {
    22: (100.0, 102.5, 99.5, 102.0),  # touches the first add at 102
    23: (102.0, 104.5, 101.5, 104.0),  # touches the second add at 104
    24: (104.0, 106.0, 103.5, 105.0),  # would touch a third add at 106: the position is full
    25: (104.0, 104.5, 99.0, 100.0),  # falls through the stop, moved to 104 - 4 = 100
}


def test_units_are_added_every_step_up_to_the_max_and_the_stop_follows_the_last_add(engine):
    df = _bars(RISING)
    result = _run(engine, df)
    (trade,) = result.trades
    assert trade.adds == (Fill(df.index[22], 102.0), Fill(df.index[23], 104.0)) and trade.units == 3
    assert (trade.entry_date, trade.entry_price, trade.size) == (df.index[21], 102.0, 750)
    assert (trade.exit_date, trade.exit_reason, trade.exit_price) == (df.index[25], ExitReason.STOP, 100.0)
    assert trade.pnl == pytest.approx(250 * ((100 - 100) + (100 - 102) + (100 - 104)))
    assert trade.r_multiple == pytest.approx(-1.5)  # against one unit's risk: 250 shares x 4
    # Every unit counts from its own fill: at the close of bar 23 the three units are up 4, 2 and 0.
    assert result.equity.iloc[23] == pytest.approx(100_000 + 250 * (4 + 2 + 0))
    assert result.equity.iloc[-1] == pytest.approx(100_000 + trade.pnl)


def test_a_gap_through_the_add_level_fills_at_the_open_and_the_next_add_counts_from_that_fill(engine):
    df = _bars({22: (103.0, 103.5, 102.5, 103.0), 23: (103.0, 105.0, 102.5, 104.5), 24: (104.0, 104.5, 100.5, 101.0)})
    (trade,) = _run(engine, df).trades
    assert [fill.price for fill in trade.adds] == [103.0, 105.0]
    # The stop moved to 105 - 4 = 101, which bar 24 trades through.
    assert (trade.exit_date, trade.exit_reason, trade.exit_price) == (df.index[24], ExitReason.STOP, 101.0)


def test_an_exit_on_a_bar_wins_over_an_add_on_that_bar(engine):
    stopped = _run(engine, _bars({22: (100.0, 103.0, 95.0, 100.0)})).trades[0]
    assert (stopped.exit_reason, stopped.exit_price, stopped.adds, stopped.size) == (ExitReason.STOP, 96.0, (), 250)

    rules = TradeRules(exits=(TargetExit(target_r=2.0),))
    target = _run(engine, _bars({22: (100.0, 109.0, 99.5, 108.0)}), rules=rules).trades[0]
    assert (target.exit_reason, target.exit_price, target.adds) == (ExitReason.TARGET, 108.0, ())


def test_exit_rules_close_the_whole_position_and_measure_from_the_first_unit(engine):
    # The 2R target sits at 100 + 8 from the first unit's reference, whatever the adds.
    df = _bars({22: (100.0, 102.5, 99.5, 102.0), 24: (102.0, 108.5, 101.5, 108.0)})
    rules = TradeRules(exits=(TargetExit(target_r=2.0),))
    (trade,) = _run(engine, df, config=replace(NO_COSTS, max_units=2), rules=rules).trades
    assert (trade.exit_reason, trade.exit_price, trade.units) == (ExitReason.TARGET, 108.0, 2)
    assert trade.pnl == pytest.approx(250 * (8 + 6)) and trade.r_multiple == pytest.approx(3.5)

    timed = _run(engine, _bars(RISING), rules=TradeRules(exits=(TimeExit(max_hold_bars=3),))).trades[0]
    assert (timed.exit_reason, timed.exit_date, timed.units) == (ExitReason.TIME, _bars({}).index[24], 3)


def test_shorts_add_below_the_last_fill_and_move_the_stop_down(engine):
    df = _bars({
        22: (100.0, 100.5, 97.5, 98.0), 23: (98.0, 98.5, 95.5, 96.0), 25: (96.0, 101.0, 95.5, 100.0),
    })  # fmt: skip
    (trade,) = _run(engine, df, side=Direction.SHORT).trades
    assert [fill.price for fill in trade.adds] == [98.0, 96.0] and trade.direction is Direction.SHORT
    assert (trade.exit_reason, trade.exit_price) == (ExitReason.STOP, 100.0)
    assert trade.pnl == pytest.approx(250 * ((100 - 100) + (98 - 100) + (96 - 100)))


def test_an_open_position_keeps_every_unit_marked_to_the_last_close(engine):
    df = _bars({22: (100.0, 102.5, 99.5, 102.0), 23: (102.0, 104.5, 101.5, 104.0)} | {i: (104.0, 105.0, 103.0, 104.0) for i in range(24, 30)})
    (trade,) = _run(engine, df).trades
    assert trade.exit_reason == ExitReason.OPEN and trade.units == 3
    assert trade.pnl == pytest.approx(250 * (4 + 2 + 0))


def test_one_unit_turns_pyramiding_off(engine):
    assert not Pyramiding.of(BacktestConfig()).enabled
    (trade,) = _run(engine, _bars(RISING), config=replace(NO_COSTS, max_units=1)).trades
    assert (trade.units, trade.size, trade.exit_reason) == (1, 250, ExitReason.OPEN)


def test_commission_and_slippage_are_paid_on_every_unit(engine):
    config = replace(NO_COSTS, commission_pct=0.1, slippage_pct=0.1)
    (trade,) = _run(engine, _bars(RISING), config=config).trades
    # The market entry and the two buy-stops, slipped against the buy; each add counts from the last fill.
    fills = [100.1]
    for _ in range(2):
        fills.append((fills[-1] + 2.0) * 1.001)
    assert trade.units == 3 and trade.entry_price == pytest.approx(sum(fills) / 3)
    exit_price = (fills[-1] - 4.0) * 0.999  # the stop moved from the last fill, slipped against the sell
    commissions = 0.001 * 250 * (sum(fills) + 3 * exit_price)
    assert trade.exit_price == pytest.approx(exit_price)
    assert trade.pnl == pytest.approx(250 * sum(exit_price - fill for fill in fills) - commissions)


def test_units_ask_for_their_add_and_their_moved_stop():
    trade = OpenTrade(Direction.LONG, entry_index=5, entry_price=100.0, reference=99.0, stop=95.0, risk=4.0)
    units = Pyramiding(max_units=3, add_every_atr=0.5).start(trade, atr=2.0)
    assert units.add_level() == 101.0 and units.orders(5).stop is None
    units.add(7, 101.5)
    assert (units.add_level(), units.orders(7).stop, units.count) == (102.5, 97.5, 2)
    units.add(9, 102.5)
    assert units.add_level() is None and units.orders(9).stop == 98.5 and units.adds == [(7, 101.5), (9, 102.5)]


def test_trades_export_counts_the_units_and_lists_the_adds():
    df = _bars(RISING)
    frame = trades_to_frame(VectorizedEngine().run("TEST", df, FixedSignal(positions=(20,)), NO_COSTS, STOP_ONLY).trades)
    days = [day.date().isoformat() for day in df.index[22:24]]
    assert frame.loc[0, "units"] == 3 and frame.loc[0, "adds"] == f"{days[0]} 102; {days[1]} 104"


# --- Both engines give identical pyramided trades -------------------------------------------------


ENGINE_CHECK_CONFIG = BacktestConfig(commission_pct=0.1, slippage_pct=0.05, max_units=4, add_every_atr=0.5)

PYRAMID_RULES = [
    TradeRules(),
    TradeRules(exits=()),
    TradeRules(exits=(TrailingStop(atr_mult=2.0),)),
    TradeRules(exits=(BreakevenStop(trigger_r=1.0, lock_r=0.2), TimeExit(max_hold_bars=40))),
    TradeRules(exits=(RatchetStop(), TargetExit(target_r=4.0))),
    TradeRules(entry=StopEntry(offset_atr=0.2, valid_bars=2), exits=(TargetExit(target_r=4.0), TimeExit(max_hold_bars=40))),
    TradeRules(entry=LimitEntry(valid_bars=2), exits=(TrailingStop(atr_mult=1.5),)),
]


@pytest.mark.parametrize("rules", PYRAMID_RULES, ids=lambda rules: f"{rules.entry.name}+" + "+".join(rule.name for rule in rules.exits))
@pytest.mark.parametrize("signal_name", ["donchian_breakout", "ema_cross_down"])
@pytest.mark.parametrize("config", [ENGINE_CHECK_CONFIG, replace(ENGINE_CHECK_CONFIG, max_units=2, add_every_atr=1.5)], ids=["4x0.5", "2x1.5"])
def test_engines_match_with_pyramiding(rules, signal_name, config):
    df = random_walk(1500, seed=31)
    signal = default_registry.create(signal_name)
    fast = VectorizedEngine().run("RW", df, signal, config, rules)
    slow = _cerebro().run("RW", df, signal, config, rules)
    assert len(fast.trades) == len(slow.trades) > 0
    assert any(trade.adds for trade in fast.trades), "the check needs pyramided positions"
    for left, right in zip(fast.trades, slow.trades):
        assert (left.entry_date, left.exit_date, left.exit_reason, left.size) == (right.entry_date, right.exit_date, right.exit_reason, right.size)
        assert [fill.date for fill in left.adds] == [fill.date for fill in right.adds]
        np.testing.assert_allclose([fill.price for fill in left.adds], [fill.price for fill in right.adds], rtol=1e-9)
        assert left.entry_price == pytest.approx(right.entry_price, rel=1e-9)
        assert left.exit_price == pytest.approx(right.exit_price, rel=1e-9)
        assert left.pnl == pytest.approx(right.pnl, rel=1e-6, abs=1e-6)
    np.testing.assert_allclose(fast.equity.to_numpy(), slow.equity.to_numpy(), rtol=1e-9)
