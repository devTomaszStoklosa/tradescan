"""Entry filters bar by bar on hand-made bars, how the trade rules combine them, and when a backtest loads the
benchmark."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from synthetic import FakeProvider, make_ohlcv, random_walk

from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.filters import (
    AdxFilter,
    AtrPercentFilter,
    FilterInputs,
    MarketFilter,
    TrendFilter,
    VolumeFilter,
    entry_filters,
)
from tradescan.backtest.rules import Bars
from tradescan.backtest.trade_rules import RuleCatalog, RuleChoice, TradeRules
from tradescan.config import Settings
from tradescan.indicators import adx
from tradescan.services import BacktestRequest, build_use_cases
from tradescan.signals import Direction

CONFIG = BacktestConfig()


def _bars(close, volume=1_000.0, start="2024-01-01") -> Bars:
    return Bars.from_frame(make_ohlcv(close, volume=volume, start=start), CONFIG.atr_period)


def _allows(rule, bars, direction=Direction.LONG, benchmark=None) -> list[bool]:
    return rule.allows(FilterInputs(bars, benchmark), direction).tolist()


def test_registry_lists_every_filter_and_only_the_market_filter_reads_the_benchmark():
    assert entry_filters.names() == ["trend", "market", "adx", "volume", "atr_pct"]
    assert [cls.name for cls in entry_filters.classes() if cls.needs_benchmark] == ["market"]


def test_trend_filter_needs_the_close_beyond_the_sma_in_the_trade_direction():
    bars = _bars([10, 11, 12, 11, 9, 8])  # SMA(3): -, -, 11, 11.33, 10.67, 9.33
    rule = TrendFilter(period=3)
    assert _allows(rule, bars) == [False, False, True, False, False, False]
    assert _allows(rule, bars, Direction.SHORT) == [False, False, False, True, True, True]


def test_market_filter_compares_the_benchmark_on_its_own_bars_and_uses_the_last_close_before_each_date():
    benchmark = pd.Series([10.0, 11.0, 12.0, 11.0, 9.0], index=pd.to_datetime(
        ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    ))  # fmt: skip
    # The ticker trades every calendar day, from before the benchmark's first bar: weekend days get Friday's close.
    dates = pd.date_range("2023-12-31", "2024-01-07", freq="D")
    bars = _bars(np.full(len(dates), 50.0), start="2023-12-31")
    bars = Bars(bars.open, bars.high, bars.low, bars.close, bars.volume, bars.atr, dates)
    rule = MarketFilter(period=3)  # benchmark above its SMA(3) on Jan 3 only, below it on Jan 4 and 5
    assert _allows(rule, bars, benchmark=benchmark) == [False, False, False, True, False, False, False, False]
    assert _allows(rule, bars, Direction.SHORT, benchmark) == [False, False, False, False, True, True, True, True]


def test_market_filter_without_the_benchmark_is_an_error():
    with pytest.raises(ValueError, match="needs the benchmark"):
        _allows(MarketFilter(), _bars([10, 11, 12]))


def test_adx_filter_needs_the_minimum_trend_strength_whatever_the_direction():
    df = random_walk(300, seed=3)
    bars = Bars.from_frame(df, CONFIG.atr_period)
    values = adx(df, 14)["adx"].to_numpy()
    rule = AdxFilter(min_adx=25)
    expected = (values >= 25).tolist()
    assert _allows(rule, bars) == expected == _allows(rule, bars, Direction.SHORT)
    assert 0 < sum(expected) < np.isfinite(values).sum()


def test_volume_filter_compares_the_bar_with_the_average_of_the_bars_before_it():
    bars = _bars([10] * 6, volume=[100, 100, 100, 150, 300, 0])  # averages of the 3 bars before: -, -, -, 100, 116.7, 183.3
    rule = VolumeFilter(period=3, min_ratio=1.5)
    assert _allows(rule, bars) == [False, False, False, True, True, False]
    assert _allows(rule, _bars([10] * 6, volume=0.0)) == [False] * 6  # no volume never passes


def test_atr_percent_filter_keeps_the_atr_inside_the_band():
    bars = _bars(np.full(30, 100.0))
    bars = Bars(bars.open, bars.high, bars.low, bars.close, bars.volume, np.r_[np.full(10, np.nan), np.linspace(0.5, 6.0, 20)], bars.dates)
    allowed = np.array(_allows(AtrPercentFilter(min_pct=1.0, max_pct=5.0), bars))
    pct = bars.atr / bars.close * 100.0
    assert not allowed[:10].any()
    np.testing.assert_array_equal(allowed[10:], (pct[10:] >= 1.0) & (pct[10:] <= 5.0))
    with pytest.raises(ValueError, match="must be below the maximum"):
        AtrPercentFilter(min_pct=5.0, max_pct=5.0)


def test_trade_rules_need_every_filter_to_allow_a_signal():
    df = make_ohlcv(np.full(40, 100.0))
    bars = Bars.from_frame(df, CONFIG.atr_period)  # flat bars: ATR is 2% of the close once warmed up
    wide, narrow = AtrPercentFilter(min_pct=1.0, max_pct=3.0), AtrPercentFilter(min_pct=3.0, max_pct=4.0)
    assert TradeRules(filters=()).prepare(bars, Direction.LONG).allowed.all()
    prepared = TradeRules(filters=(wide,)).prepare(bars, Direction.LONG)
    assert prepared.plan(13, 100_000.0, CONFIG) is not None and prepared.plan(5, 100_000.0, CONFIG) is None
    blocked = TradeRules(filters=(wide, VolumeFilter(min_ratio=2.0))).prepare(bars, Direction.LONG)
    assert not blocked.allowed.any() and blocked.plan(13, 100_000.0, CONFIG) is None
    assert not TradeRules(filters=(narrow,)).prepare(bars, Direction.LONG).allowed.any()


def test_trade_rules_reject_repeated_filters_and_report_whether_they_need_the_benchmark():
    with pytest.raises(ValueError, match="Entry filter\\(s\\) given more than once: trend"):
        TradeRules(filters=(TrendFilter(), AdxFilter(), TrendFilter(period=50)))
    assert not TradeRules(filters=(TrendFilter(),)).needs_benchmark
    rules = TradeRules(filters=(TrendFilter(), MarketFilter()))
    close = pd.Series([1.0, 2.0])
    assert rules.needs_benchmark and rules.with_benchmark(close).benchmark_close is close
    assert rules.with_benchmark(close) == rules  # the benchmark's closes are data, not part of the rules


def test_catalog_builds_filters_with_validated_parameters_and_none_by_default():
    catalog = RuleCatalog()
    assert catalog.build().filters == ()
    rules = catalog.build(filters=[RuleChoice("trend", {"period": 50}), RuleChoice("volume")])
    assert rules.filters == (TrendFilter(period=50), VolumeFilter())
    assert rules.filters[0].describe() == "Close above SMA(50) for longs, below it for shorts"
    with pytest.raises(ValueError, match="Unknown filter rule 'nope'"):
        catalog.build(filters=[RuleChoice("nope")])
    with pytest.raises(ValueError, match="between 1 and 100"):
        catalog.build(filters=[RuleChoice("adx", {"min_adx": 0})])


def test_backtest_loads_the_benchmark_only_when_a_filter_compares_it():
    frames = {"AAA": random_walk(1500, seed=1), "SPY": random_walk(1500, seed=6), "QQQ": random_walk(1500, seed=7)}
    provider = FakeProvider(frames)
    backtest = build_use_cases(Settings(), provider).backtest
    request = BacktestRequest(ticker="AAA", signal="connors_rsi2_long", period="max")

    trend = backtest.run(replace(request, filters=(RuleChoice("trend", {"period": 50}),)))
    assert trend.benchmark is None and provider.calls[-1][0] == ("AAA",)
    unfiltered = backtest.run(request)
    assert len(trend.runs[0].result.trades) < len(unfiltered.runs[0].result.trades)

    market = backtest.run(replace(request, filters=(RuleChoice("market"),)))
    assert market.benchmark == "SPY" and provider.calls[-1][0] == ("AAA", "SPY")  # the settings' scan benchmark
    assert market.rules.benchmark_close.equals(frames["SPY"]["close"])
    chosen = backtest.run(replace(request, filters=(RuleChoice("market"),), benchmark="qqq"))
    assert chosen.benchmark == "QQQ" and provider.calls[-1][0] == ("AAA", "QQQ")
    with pytest.raises(ValueError, match="No data for the benchmark NOPE, which the market filter compares"):
        backtest.run(replace(request, filters=(RuleChoice("market"),), benchmark="nope"))
