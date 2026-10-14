"""Price history with moving averages and signal events for charting."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import chart_out
from tradescan.services import ChartRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["chart"])

    @router.post("/chart", response_model=schemas.ChartOut)
    def chart(body: schemas.ChartIn) -> schemas.ChartOut:
        """POST, so the markers can use the same signal parameters as the scan or backtest they belong to."""
        context.check_signals(body.signals)
        request = ChartRequest(
            ticker=body.ticker, signals=tuple(body.signals), signal_params=body.signal_params, period=body.period
        )
        return chart_out(context.use_cases.chart.run(request))

    return router
