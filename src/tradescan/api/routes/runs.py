"""Pinned runs kept on the server for Compare; the UI owns the snapshot inside each one."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from tradescan.api.context import ApiContext
from tradescan.api.mappers.runs import pinned_run_out
from tradescan.api.schemas.common import ErrorOut
from tradescan.api.schemas.runs import PinnedRunIn, PinnedRunOut, PinnedRunPatchIn
from tradescan.storage.runs import PinnedRun

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorOut, "description": "No pinned run has this id"}}


def build_router(context: ApiContext) -> APIRouter:
    router = APIRouter(tags=["runs"])
    store = context.runs

    @router.get("/runs", response_model=list[PinnedRunOut])
    def list_runs() -> list[PinnedRunOut]:
        return [pinned_run_out(run) for run in store.runs()]

    @router.post(
        "/runs",
        response_model=PinnedRunOut,
        status_code=201,
        responses={409: {"model": ErrorOut, "description": "The id is already pinned or the slot is taken"}},
    )
    def pin_run(body: PinnedRunIn) -> PinnedRunOut:
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

    @router.patch("/runs/{run_id}", response_model=PinnedRunOut, responses=_NOT_FOUND)
    def update_run(run_id: str, body: PinnedRunPatchIn) -> PinnedRunOut:
        return pinned_run_out(store.update(run_id, name=body.name, hidden=body.hidden))

    @router.delete("/runs/{run_id}", status_code=204, responses=_NOT_FOUND)
    def unpin_run(run_id: str) -> None:
        store.remove(run_id)

    @router.delete("/runs", status_code=204)
    def clear_runs() -> None:
        store.clear()

    return router
