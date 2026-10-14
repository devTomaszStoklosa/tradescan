"""Registry of signal classes. New signals plug in with `@register` without touching other code."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from tradescan.params import GroupOverrides, Overrides, check_group, with_overrides
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

    def create(self, name: str, params: Overrides | None = None) -> Signal:
        """A signal with its default parameters, or with `params` validated against their declared ranges."""
        try:
            cls = self._classes[name]
        except KeyError:
            raise KeyError(f"Unknown signal '{name}'. Run `tradescan list-signals` to see all names.") from None
        return with_overrides(cls(), params, owner=name)

    def check_params(self, params: GroupOverrides) -> None:
        """Validate overrides even for signals a filter leaves out, so a bad value never passes silently."""
        check_group(params, self.names(), "signal(s)")
        for name, values in params.items():
            self.create(name, values)

    def select(
        self,
        names: Sequence[str] | None = None,
        families: Collection[Family] | None = None,
        directions: Collection[Direction] | None = None,
        params: GroupOverrides | None = None,
    ) -> list[Signal]:
        """Signals matching the filters; `params` maps signal names to their parameter overrides."""
        params = params or {}
        self.check_params(params)
        signals = [self.create(name, params.get(name)) for name in (names or self.names())]
        return [
            signal
            for signal in signals
            if (not families or signal.family in families) and (not directions or signal.direction in directions)
        ]


default_registry = SignalRegistry()
register = default_registry.register
