"""Map a market report, and the regime a scan reports too."""

from __future__ import annotations

from tradescan.api.mappers.common import finite
from tradescan.api.schemas.market import MarketOut, RegimeOut
from tradescan.regime import MarketRegime
from tradescan.services.market import MarketReport


def regime_out(regime: MarketRegime) -> RegimeOut:
    return RegimeOut(
        benchmark=regime.benchmark,
        benchmark_close=finite(regime.benchmark_close),
        benchmark_above_slow=regime.benchmark_above_slow,
        benchmark_fast_above_slow=regime.benchmark_fast_above_slow,
        pct_above_fast=finite(regime.pct_above_fast),
        pct_above_slow=finite(regime.pct_above_slow),
        new_highs=regime.new_highs,
        new_lows=regime.new_lows,
        universe_size=regime.universe_size,
        regime=regime.regime.value,
    )


def market_out(report: MarketReport) -> MarketOut:
    return MarketOut(universe=report.universe.name, regime=regime_out(report.regime), missing=report.missing)
