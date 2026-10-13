"""Price history with moving averages and signal events for charting."""

from __future__ import annotations

from fastapi import APIRouter, Query

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import chart_out
from tradescan.services import ChartRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["chart"])

    @router.get("/chart/{ticker}", response_model=schemas.ChartOut)
    def chart(
        ticker: str,
        signals: list[str] = Query(default_factory=list, description="Signals whose events to mark"),
        period: str | None = None,
    ) -> schemas.ChartOut:
        context.check_signals(signals)
        return chart_out(context.use_cases.chart.run(ChartRequest(ticker=ticker, signals=tuple(signals), period=period)))

    return router
