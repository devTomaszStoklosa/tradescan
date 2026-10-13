"""Single-ticker backtest with one or both engines."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext, account_overrides
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
                account=account_overrides(body.account),
                atr_mult=body.atr_mult,
                target_r=body.target_r,
                max_hold_bars=body.max_hold_bars,
                commission_pct=body.commission_pct,
                slippage_pct=body.slippage_pct,
                period=body.period,
            )
        )
        return backtest_out(report)

    return router
