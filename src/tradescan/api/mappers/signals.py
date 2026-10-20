"""Map signals to the models of GET /api/signals."""

from __future__ import annotations

from tradescan.api.mappers.common import param_spec_out
from tradescan.api.schemas.signals import SignalOut
from tradescan.scoring import Scorer
from tradescan.signals.base import Signal


def signal_out(signal: Signal, scorer: Scorer) -> SignalOut:
    return SignalOut(
        name=signal.name,
        family=signal.family,
        direction=signal.direction,
        weight=scorer.weight(signal),
        description=signal.describe(),
        template=signal.description,
        params=[param_spec_out(spec) for spec in signal.parameters()],
    )
