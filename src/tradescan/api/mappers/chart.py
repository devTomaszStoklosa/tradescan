"""Map chart data."""

from __future__ import annotations

from tradescan.api.mappers.common import day, points
from tradescan.api.schemas.chart import Candle, ChartEventOut, ChartOut
from tradescan.services.chart import ChartData


def chart_out(data: ChartData) -> ChartOut:
    bars = data.bars
    return ChartOut(
        ticker=data.ticker,
        candles=[
            Candle(time=day(index), open=row.open, high=row.high, low=row.low, close=row.close, volume=row.volume)
            for index, row in zip(bars.index, bars.itertuples(index=False), strict=True)
        ],
        sma_fast=points(data.sma_fast),
        sma_slow=points(data.sma_slow),
        events=[
            ChartEventOut(time=day(event.date), signal=event.signal, direction=event.direction) for event in data.events
        ],
    )
