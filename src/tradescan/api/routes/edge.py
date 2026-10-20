"""Historical signal edge."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import edge_out
from tradescan.services.edge import EdgeRequest


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["edge"])

    @router.post("/edge", response_model=schemas.EdgeOut)
    def edge(body: schemas.EdgeIn) -> schemas.EdgeOut:
        report = context.use_cases.edge.run(
            EdgeRequest(
                universe=context.universe(body),
                signals=context.signal_filter(body),
                signal_params=body.signal_params,
                horizons=tuple(body.horizons),
                min_events=body.min_events,
                period=body.period,
            )
        )
        return edge_out(report)

    return router
