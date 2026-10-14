"""Single-ticker backtest with one or both engines."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import backtest_out
from tradescan.services import BacktestRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["backtest"])

    @router.post("/backtest", response_model=schemas.BacktestOut)
    def backtest(body: schemas.BacktestIn) -> schemas.BacktestOut:
        context.check_signals([body.signal])
        report = context.use_cases.backtest.run(
            BacktestRequest(
                ticker=body.ticker,
                signal=body.signal,
                engines=tuple(body.engines),
                params=body.params,
                settings=body.settings,
                period=body.period,
            )
        )
        return backtest_out(report)

    return router
