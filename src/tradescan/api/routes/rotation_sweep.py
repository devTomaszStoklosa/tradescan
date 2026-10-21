"""Rotation sweep: one rotation setup over a grid of one or two parameters, in-sample and out-of-sample."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api.context import ApiContext
from tradescan.api.mappers.rotation_sweep import rotation_sweep_out
from tradescan.api.routes.rotation import rotation_request
from tradescan.api.schemas.rotation_sweep import RotationSweepIn, RotationSweepOut
from tradescan.backtest.rotation_sweep import RotationSweepAxis
from tradescan.services.rotation_sweep import RotationSweepRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["backtest"])

    @router.post("/rotation-sweep", response_model=RotationSweepOut)
    def rotation_sweep(body: RotationSweepIn) -> RotationSweepOut:
        axes = tuple(
            RotationSweepAxis(target=axis.target, name=axis.name, values=tuple(axis.values), owner=axis.owner or "")
            for axis in body.axes
        )
        request = RotationSweepRequest(setup=rotation_request(context, body, ()), axes=axes)
        return rotation_sweep_out(context.use_cases.rotation_sweep.run(request))

    return router
