"""Signal scan."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api.context import ApiContext
from tradescan.api.mappers import scan_out
from tradescan.api.schemas.scan import ScanIn, ScanOut
from tradescan.services.scan import ScanRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["scan"])

    @router.post("/scan", response_model=ScanOut)
    def scan(body: ScanIn) -> ScanOut:
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
