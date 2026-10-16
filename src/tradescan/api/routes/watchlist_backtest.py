"""One backtest setup on every ticker of a watchlist: per-ticker metrics, pooled trades and their spread."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import watchlist_backtest_out
from tradescan.api.routes.backtest import backtest_request
from tradescan.services import WatchlistBacktestRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["backtest"])

    @router.post("/watchlist-backtest", response_model=schemas.WatchlistBacktestOut)
    def watchlist_backtest(body: schemas.WatchlistBacktestIn) -> schemas.WatchlistBacktestOut:
        context.check_signals([body.signal])
        request = WatchlistBacktestRequest(universe=context.universe(body), setup=backtest_request(body, "", ()))
        return watchlist_backtest_out(context.use_cases.watchlist_backtest.run(request))

    return router
