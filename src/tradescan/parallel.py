"""Task runners: how per-ticker work is executed. Use cases depend on the `TaskRunner` protocol only."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from typing import Protocol, TypeVar

T = TypeVar("T")
R = TypeVar("R")


class TaskRunner(Protocol):
    def map(self, function: Callable[[T], R], items: Sequence[T]) -> list[R]:
        """Apply `function` to every item and return the results in input order."""
        ...


class SequentialRunner:
    def map(self, function: Callable[[T], R], items: Sequence[T]) -> list[R]:
        return [function(item) for item in items]


class ProcessRunner:
    """Spreads items over worker processes, one per core.

    Starting processes costs a few seconds on Windows, so inputs smaller than `min_items` run
    in the current process. `function` and the items must be picklable (module-level callables).
    """

    def __init__(self, workers: int | None = None, min_items: int = 40) -> None:
        self._workers = max(1, workers or os.cpu_count() or 1)
        self._min_items = min_items

    def map(self, function: Callable[[T], R], items: Sequence[T]) -> list[R]:
        if self._workers == 1 or len(items) < self._min_items:
            return [function(item) for item in items]
        # A few chunks per worker balances uneven tickers without paying per-item overhead.
        chunk = max(1, len(items) // (self._workers * 4))
        with ProcessPoolExecutor(max_workers=self._workers) as pool:
            return list(pool.map(function, items, chunksize=chunk))
