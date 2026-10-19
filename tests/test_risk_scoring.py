import math

import pandas as pd
import pytest

from tradescan.context import TickerContext, Trend
from tradescan.risk import RiskPlanner, position_size, trade_levels
from tradescan.scoring import Scorer
from tradescan.signals import Direction, default_registry


def _context(daily=Trend.UP, weekly=Trend.UP):
    return TickerContext(
        ticker="AAA", date=pd.Timestamp("2024-01-02"), close=100.0, change_pct=1.0, atr=2.0, atr_pct=2.0,
        adx=25.0, daily_trend=daily, weekly_trend=weekly, rs_raw=0.1,
    )  # fmt: skip


def test_trade_levels_long_and_short():
    assert trade_levels(Direction.LONG, 100.0, 2.0, 2.0, (2.0, 3.0)) == (96.0, (108.0, 112.0), 4.0)
    assert trade_levels(Direction.SHORT, 100.0, 2.0, 2.0, (2.0,)) == (104.0, (92.0,), 4.0)


def test_position_size_risk_budget_value_cap_and_lots():
    assert position_size(100_000, 100.0, 4.0, 1.0, 100.0) == 250  # 1000 risk / 4 per share
    assert position_size(100_000, 100.0, 0.5, 1.0, 25.0) == 250  # capped at 25k value
    assert position_size(10_000, 60_000.0, 3_000.0, 1.0, 25.0, lot_size=0.0001) == pytest.approx(0.0333)
    assert position_size(10_000, 100.0, 0.0, 1.0, 25.0) == 0.0


def test_risk_planner_reports_amounts():
    plan = RiskPlanner(100_000, 1.0, 100.0, 2.0, (2.0, 3.0)).plan(Direction.LONG, 100.0, 2.0)
    assert plan.stop == 96.0
    assert plan.size == 250
    assert plan.risk_amount == pytest.approx(1_000.0)
    assert plan.position_value == pytest.approx(25_000.0)


def test_scorer_weights_and_alignment():
    scorer = Scorer({"breakout": 1.5}, {"golden_cross": 3.0}, trend_bonus=1.0, weekly_bonus=0.5, rs_bonus=1.0)
    breakout = default_registry.create("donchian_breakout")
    golden = default_registry.create("golden_cross")
    macd = default_registry.create("macd_cross_up")
    assert scorer.weight(breakout) == 1.5
    assert scorer.weight(golden) == 3.0
    assert scorer.weight(macd) == 1.0

    long_score = scorer.score(Direction.LONG, [breakout, macd], _context(), rs_percentile=90.0)
    assert (long_score.signals, long_score.trend, long_score.weekly, long_score.relative_strength) == (
        2.5,
        1.0,
        0.5,
        1.0,
    )
    assert long_score.total == pytest.approx(5.0)

    short_score = scorer.score(Direction.SHORT, [macd], _context(weekly=Trend.NEUTRAL), rs_percentile=math.nan)
    assert (short_score.trend, short_score.weekly, short_score.relative_strength) == (-1.0, 0.0, 0.0)
