"""Chart: one ticker's bars with its moving averages and the signals that fired."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from tradescan.indicators import sma
from tradescan.params import GroupOverrides
from tradescan.services.market_data import MarketData
from tradescan.signals.base import Direction
from tradescan.signals.registry import SignalRegistry


@dataclass(frozen=True)
class ChartRequest:
    ticker: str
    signals: tuple[str, ...] = ()
    signal_params: GroupOverrides = field(default_factory=dict)
    period: str | None = None
    interval: str | None = None


@dataclass(frozen=True)
class SignalEvent:
    date: pd.Timestamp
    signal: str
    direction: Direction


@dataclass(frozen=True)
class ChartData:
    ticker: str
    bars: pd.DataFrame
    sma_fast: pd.Series
    sma_slow: pd.Series
    events: list[SignalEvent]


class ChartUseCase:
    def __init__(
        self,
        market_data: MarketData,
        registry: SignalRegistry,
        fast_period: int = 50,
        slow_period: int = 200,
    ) -> None:
        self._market_data = market_data
        self._registry = registry
        self._fast_period = fast_period
        self._slow_period = slow_period

    def run(self, request: ChartRequest) -> ChartData:
        ticker = request.ticker.upper()
        self._registry.check_params(request.signal_params)
        signals = [self._registry.create(name, request.signal_params.get(name)) for name in request.signals]
        loaded = self._market_data.load([ticker], request.period, request.interval)
        if ticker not in loaded.frames:
            raise ValueError(f"No data for {ticker}")
        df = loaded.frames[ticker]
        events = [
            SignalEvent(date=date, signal=signal.name, direction=signal.direction)
            for signal in signals
            for date in df.index[signal.events(df).to_numpy()]
        ]
        events.sort(key=lambda event: event.date)
        return ChartData(
            ticker=ticker,
            bars=df,
            sma_fast=sma(df["close"], self._fast_period),
            sma_slow=sma(df["close"], self._slow_period),
            events=events,
        )
