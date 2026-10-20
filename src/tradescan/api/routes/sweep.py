"""Parameter sweep: one backtest setup over a grid of one or two parameters, in-sample and out-of-sample."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api.context import ApiContext
from tradescan.api.mappers.sweep import sweep_out
from tradescan.api.routes.backtest import backtest_request
from tradescan.api.schemas.sweep import SweepIn, SweepOut
from tradescan.backtest.sweep import SweepAxis
from tradescan.services.sweep import SweepRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["backtest"])

    @router.post("/sweep", response_model=SweepOut)
    def sweep(body: SweepIn) -> SweepOut:
        context.check_signals([body.signal])
        report = context.use_cases.sweep.run(
            SweepRequest(setup=backtest_request(body, body.ticker, ()), axes=sweep_axes(body))
        )
        return sweep_out(report)

    return router


def sweep_axes(body: SweepIn) -> tuple[SweepAxis, ...]:
    """The swept axes of a sweep or a walk-forward request."""
    return tuple(
        SweepAxis(target=axis.target, name=axis.name, values=tuple(axis.values), owner=axis.owner or "")
        for axis in body.axes
    )
