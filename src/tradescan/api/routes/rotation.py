"""A momentum rotation over a watchlist with one shared equity."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import rotation_out
from tradescan.api.routes.backtest import rule_choice
from tradescan.services.rotation import RotationRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["backtest"])

    @router.post("/rotation-backtest", response_model=schemas.RotationOut)
    def rotation_backtest(body: schemas.RotationIn) -> schemas.RotationOut:
        request = RotationRequest(
            universe=context.universe(body),
            ranking=rule_choice(body.ranking) if body.ranking else None,
            weighting=rule_choice(body.weighting) if body.weighting else None,
            rebalance=body.rebalance,
            safe_asset=body.safe_asset,
            settings=body.settings,
            benchmark=body.benchmark,
            period=body.period,
        )
        return rotation_out(context.use_cases.rotation.run(request))

    return router
