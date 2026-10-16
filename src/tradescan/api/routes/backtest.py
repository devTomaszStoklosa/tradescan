"""Single-ticker backtest with one or both engines."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import backtest_out
from tradescan.backtest.trade_rules import RuleChoice
from tradescan.services import BacktestRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["backtest"])

    @router.post("/backtest", response_model=schemas.BacktestOut)
    def backtest(body: schemas.BacktestIn) -> schemas.BacktestOut:
        context.check_signals([body.signal])
        report = context.use_cases.backtest.run(backtest_request(body, tuple(body.engines)))
        return backtest_out(report)

    return router


def backtest_request(body: schemas.BacktestSetupIn, engines: tuple[str, ...]) -> BacktestRequest:
    return BacktestRequest(
        ticker=body.ticker,
        signal=body.signal,
        engines=engines,
        params=body.params,
        settings=body.settings,
        entry=_choice(body.entry) if body.entry else None,
        exits=None if body.exits is None else tuple(_choice(rule) for rule in body.exits),
        filters=tuple(_choice(rule) for rule in body.filters),
        benchmark=body.benchmark,
        period=body.period,
    )


def _choice(rule: schemas.RuleIn) -> RuleChoice:
    return RuleChoice(name=rule.name, params=rule.params)
