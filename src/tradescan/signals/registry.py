"""Registry of signal classes. New signals plug in with `@register` without touching other code."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any

from tradescan.signals.base import Direction, Family, Signal


class SignalRegistry:
    def __init__(self) -> None:
        self._classes: dict[str, type[Signal]] = {}

    def register(self, cls: type[Signal]) -> type[Signal]:
        if cls.name in self._classes:
            raise ValueError(f"Duplicate signal name: {cls.name}")
        self._classes[cls.name] = cls
        return cls

    def names(self) -> list[str]:
        return sorted(self._classes)

    def create(self, name: str, **params: Any) -> Signal:
        try:
            cls = self._classes[name]
        except KeyError:
            raise KeyError(f"Unknown signal '{name}'. Run `tradescan list-signals` to see all names.") from None
        return cls(**params)

    def select(
        self,
        names: Sequence[str] | None = None,
        families: Collection[Family] | None = None,
        directions: Collection[Direction] | None = None,
    ) -> list[Signal]:
        signals = [self.create(name) for name in (names or self.names())]
        return [
            signal
            for signal in signals
            if (not families or signal.family in families) and (not directions or signal.direction in directions)
        ]


default_registry = SignalRegistry()
register = default_registry.register
