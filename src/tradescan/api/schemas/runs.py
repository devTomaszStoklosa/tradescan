"""Models of the pinned runs at /api/runs."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from tradescan.api.schemas.common import RequestModel
from tradescan.storage.runs import MAX_PINNED_RUNS


class PinnedRunIn(RequestModel):
    id: str = Field(min_length=1, max_length=100)
    slot: int = Field(ge=1, le=MAX_PINNED_RUNS, description="The run's number and colour in Compare")
    name: str = Field(max_length=200)
    hidden: bool = Field(description="True when Compare leaves the run out of its tables and chart")
    pinned_at: str = Field(max_length=40, description="When the run was pinned, as an ISO 8601 time")
    format: int = Field(ge=1, description="The UI's runs-file version the snapshot was written in")
    snapshot: dict[str, Any] = Field(description="The run as the UI keeps it; the server stores it unchanged")


class PinnedRunPatchIn(RequestModel):
    name: str | None = Field(None, max_length=200)
    hidden: bool | None = None


class PinnedRunOut(PinnedRunIn):
    """A pinned run as the server stores it."""
