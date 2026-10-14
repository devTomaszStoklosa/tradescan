"""Health check and the defaults and parameter declarations the UI builds its forms from."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan import __version__
from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import section_out
from tradescan.config import adjustable_sections
from tradescan.signals.base import Family


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["meta"])
    settings = context.settings

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @router.get("/config", response_model=schemas.ConfigOut)
    def config() -> schemas.ConfigOut:
        return schemas.ConfigOut(
            version=__version__,
            scan_period=settings.data.period,
            backtest_period=settings.backtest.period,
            benchmark=settings.scan.benchmark,
            sections=[section_out(section) for section in adjustable_sections(settings)],
            families=list(Family),
            engines=context.use_cases.backtest.engine_names,
        )

    return router
