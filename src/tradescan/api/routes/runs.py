"""Pinned runs kept on the server for Compare; the UI owns the snapshot inside each one."""

from __future__ import annotations

from fastapi import APIRouter

from tradescan.api import schemas
from tradescan.api.context import ApiContext
from tradescan.api.mappers import pinned_run_out
from tradescan.storage.runs import PinnedRun

_NOT_FOUND = {404: {"model": schemas.ErrorOut, "description": "No pinned run has this id"}}


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["runs"])
    store = context.runs

    @router.get("/runs", response_model=list[schemas.PinnedRunOut])
    def list_runs() -> list[schemas.PinnedRunOut]:
        return [pinned_run_out(run) for run in store.runs()]

    @router.post(
        "/runs",
        response_model=schemas.PinnedRunOut,
        status_code=201,
        responses={409: {"model": schemas.ErrorOut, "description": "The id is already pinned or the slot is taken"}},
    )
    def pin_run(body: schemas.PinnedRunIn) -> schemas.PinnedRunOut:
        run = PinnedRun(
            id=body.id,
            slot=body.slot,
            name=body.name,
            hidden=body.hidden,
            pinned_at=body.pinned_at,
            format=body.format,
            snapshot=body.snapshot,
        )
        return pinned_run_out(store.add(run))

    @router.patch("/runs/{run_id}", response_model=schemas.PinnedRunOut, responses=_NOT_FOUND)
    def update_run(run_id: str, body: schemas.PinnedRunPatchIn) -> schemas.PinnedRunOut:
        return pinned_run_out(store.update(run_id, name=body.name, hidden=body.hidden))

    @router.delete("/runs/{run_id}", status_code=204, responses=_NOT_FOUND)
    def unpin_run(run_id: str) -> None:
        store.remove(run_id)

    @router.delete("/runs", status_code=204)
    def clear_runs() -> None:
        store.clear()

    return router
