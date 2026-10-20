"""One backtest setup on every ticker of a watchlist with one shared equity, on one or both engines."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api.context import ApiContext
from tradescan.api.mappers import portfolio_out
from tradescan.api.routes.backtest import backtest_request, rule_choice
from tradescan.api.schemas.portfolio import PortfolioIn, PortfolioOut
from tradescan.services.portfolio import PortfolioRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["backtest"])

    @router.post("/portfolio-backtest", response_model=PortfolioOut)
    def portfolio_backtest(body: PortfolioIn) -> PortfolioOut:
        context.check_signals([body.signal])
        request = PortfolioRequest(
            universe=context.universe(body),
            setup=backtest_request(body, "", tuple(body.engines)),
            priority=rule_choice(body.priority) if body.priority else None,
            score_signal_params=body.score_signal_params,
        )
        return portfolio_out(context.use_cases.portfolio.run(request))

    return router
