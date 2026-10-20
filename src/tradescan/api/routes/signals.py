"""Signal library."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api.context import ApiContext
from tradescan.api.mappers import signal_out
from tradescan.api.schemas.signals import SignalOut


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["signals"])

    @router.get("/signals", response_model=list[SignalOut])
    def list_signals() -> list[SignalOut]:
        return [signal_out(signal, context.scorer) for signal in context.registry.select()]

    return router
