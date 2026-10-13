"""Signal scan."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext, account_overrides
from tradescan.api.mappers import scan_out
from tradescan.services import ScanRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["scan"])

    @router.post("/scan", response_model=schemas.ScanOut)
    def scan(body: schemas.ScanIn) -> schemas.ScanOut:
        report = context.use_cases.scan.run(
            ScanRequest(
                universe=context.universe(body),
                signals=context.signal_filter(body),
                account=account_overrides(body.account),
                fresh_bars=body.fresh_bars,
                min_score=body.min_score,
                benchmark=body.benchmark,
                period=body.period,
            )
        )
        return scan_out(report, context.scorer)

    return router
