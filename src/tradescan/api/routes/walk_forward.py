"""Walk-forward analysis: one setup re-tuned on rolling in-sample windows and traded on the windows after them."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import walk_forward_out
from tradescan.api.routes.backtest import backtest_request
from tradescan.api.routes.sweep import sweep_axes
from tradescan.services import WalkForwardRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["backtest"])

    @router.post("/walk-forward", response_model=schemas.WalkForwardOut)
    def walk_forward(body: schemas.WalkForwardIn) -> schemas.WalkForwardOut:
        context.check_signals([body.signal])
        request = WalkForwardRequest(
            setup=backtest_request(body, body.ticker, ()),
            axes=sweep_axes(body),
            scheme=body.scheme,
            metric=body.metric,
        )
        return walk_forward_out(context.use_cases.walk_forward.run(request))

    return router
