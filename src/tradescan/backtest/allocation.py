"""How a portfolio decides, at one close, which of the signals that fired get an entry order and at what size.

Both portfolio engines call `allocate` with the same inputs, so they take the same signals:

* the signals are ranked by their priority score, the highest first; ties and signals without a score keep
  the watchlist order, after every scored signal;
* a signal needs a free slot: open positions plus entry orders waiting to fill stay below `max_positions`;
* its size is the one the entry plan has (risk per trade, max position, lot size, all from the shared
  equity), shrunk to fit when its value at the entry reference would take the gross exposure (open positions
  at this close plus waiting orders at their reference) above `max_exposure_pct` of equity. Less than one
  lot leaves no room for it.

On a gap, a fill can be worth more than its value at the reference, so exposure can end slightly above the cap,
the same way a position can end slightly above the max position.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

from tradescan.backtest.trade_rules import EntryPlan


@dataclass(frozen=True)
class PortfolioConfig:
    max_positions: int = 10  # open positions plus entry orders waiting to fill
    max_exposure_pct: float = 100.0  # gross value of positions and waiting orders, % of equity


@dataclass(frozen=True)
class Candidate:
    """A signal at the close of bar `index` of the `ticker`-th ticker, with the order it would place."""

    ticker: int  # position in the watchlist
    index: int  # bar in the ticker's own bars
    score: float  # priority; NaN without one
    plan: EntryPlan


@dataclass(frozen=True)
class Allocation:
    accepted: tuple[Candidate, ...]  # in priority order, each with its final size
    no_slot: int  # signals skipped because every slot was taken
    no_room: int  # signals skipped because less than one lot fitted under the exposure cap


def _priority_order(candidate: Candidate) -> tuple[bool, float, int]:
    missing = math.isnan(candidate.score)
    return (missing, 0.0 if missing else -candidate.score, candidate.ticker)


def rank(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Highest score first; ties and missing scores keep the watchlist order, missing scores last."""
    return sorted(candidates, key=_priority_order)


def fit(plan: EntryPlan, room: float, lot_size: float) -> EntryPlan | None:
    """The plan with its size cut to the largest number of lots worth at most `room` at the entry reference."""
    if plan.size * plan.reference <= room:
        return plan
    if room <= 0 or plan.reference <= 0:
        return None
    size = round(math.floor(room / plan.reference / lot_size + 1e-9) * lot_size, 10)
    return replace(plan, size=size) if size > 0 else None


def allocate(
    candidates: Sequence[Candidate],
    slots_used: int,
    exposure: float,
    equity: float,
    portfolio: PortfolioConfig,
    lot_size: float,
) -> Allocation:
    """`slots_used` counts the open positions and waiting orders, `exposure` their gross value (see the module)."""
    free = portfolio.max_positions - slots_used
    limit = equity * portfolio.max_exposure_pct / 100.0
    accepted: list[Candidate] = []
    no_slot = no_room = 0
    for candidate in rank(candidates):
        if free <= 0:
            no_slot += 1
            continue
        plan = fit(candidate.plan, limit - exposure, lot_size)
        if plan is None:
            no_room += 1
            continue
        accepted.append(replace(candidate, plan=plan))
        exposure += plan.size * plan.reference
        free -= 1
    return Allocation(tuple(accepted), no_slot, no_room)
