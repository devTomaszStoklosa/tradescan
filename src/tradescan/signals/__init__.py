"""Signal library. Importing this package registers every built-in signal in `default_registry`."""

from tradescan.signals import breakout, mean_reversion, momentum, pattern, trend, volume  # noqa: F401
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.registry import SignalRegistry, default_registry, register

__all__ = ["Direction", "Family", "Signal", "SignalRegistry", "default_registry", "register"]
