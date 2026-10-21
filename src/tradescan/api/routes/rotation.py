"""A momentum rotation over a watchlist with one shared equity, on one or both engines."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api.context import ApiContext
from tradescan.api.mappers.rotation import rotation_out
from tradescan.api.routes.backtest import rule_choice
from tradescan.api.schemas.rotation import RotationIn, RotationOut, RotationSetupIn
from tradescan.services.rotation import RotationRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["backtest"])

    @router.post("/rotation-backtest", response_model=RotationOut)
    def rotation_backtest(body: RotationIn) -> RotationOut:
        request = rotation_request(context, body, tuple(body.engines))
        return rotation_out(context.use_cases.rotation.run(request))

    return router


def rotation_request(context: ApiContext, body: RotationSetupIn, engines: tuple[str, ...]) -> RotationRequest:
    """The rotation of a rotation or a rotation sweep request."""
    return RotationRequest(
        universe=context.universe(body),
        ranking=rule_choice(body.ranking) if body.ranking else None,
        weighting=rule_choice(body.weighting) if body.weighting else None,
        rebalance=body.rebalance,
        safe_asset=body.safe_asset,
        settings=body.settings,
        benchmark=body.benchmark,
        period=body.period,
        engines=engines,
    )
