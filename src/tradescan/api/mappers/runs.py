"""Map pinned runs."""

from __future__ import annotations

from tradescan.api.schemas.runs import PinnedRunOut
from tradescan.storage.runs import PinnedRun


def pinned_run_out(run: PinnedRun) -> PinnedRunOut:
    return PinnedRunOut(
        id=run.id,
        slot=run.slot,
        name=run.name,
        hidden=run.hidden,
        pinned_at=run.pinned_at,
        format=run.format,
        snapshot=run.snapshot,
    )
