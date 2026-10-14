"""Signal scan."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
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
                settings=body.settings,
                signal_params=body.signal_params,
                benchmark=body.benchmark,
                period=body.period,
            )
        )
        return scan_out(report)

    return router
