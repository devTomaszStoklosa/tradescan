"""Market regime."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import market_out
from tradescan.services.market import MarketRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["market"])

    @router.post("/market", response_model=schemas.MarketOut)
    def market(body: schemas.MarketIn) -> schemas.MarketOut:
        report = context.use_cases.market.run(
            MarketRequest(
                universe=context.universe(body), settings=body.settings, benchmark=body.benchmark, period=body.period
            )
        )
        return market_out(report)

    return router
