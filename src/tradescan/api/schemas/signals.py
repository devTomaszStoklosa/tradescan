"""Models of GET /api/signals."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tradescan.api.schemas.common import ParamSpecOut
from tradescan.signals.base import Direction, Family


class SignalOut(BaseModel):
    name: str
    family: Family
    direction: Direction
    weight: float
    description: str = Field(description="The rule with the default parameters filled in")
    template: str = Field(description='The rule with {parameter} placeholders; format specs "", "g" and ".0%"')
    params: list[ParamSpecOut]
