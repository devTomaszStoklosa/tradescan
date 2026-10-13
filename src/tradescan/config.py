"""Application settings loaded from a TOML file.

Every section and key is optional; anything missing falls back to the defaults below.
Unknown keys raise an error so typos in the config file do not go unnoticed.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


def _default_family_weights() -> dict[str, float]:
    return {
        "trend": 1.0,
        "momentum": 1.0,
        "breakout": 1.5,
        "mean_reversion": 1.0,
        "volume": 1.0,
        "pattern": 0.5,
    }


@dataclass(frozen=True)
class DataSettings:
    period: str = "5y"
    interval: str = "1d"
    cache_dir: str = ".cache"
    cache_ttl_hours: float = 12.0


@dataclass(frozen=True)
class AccountSettings:
    equity: float = 100_000.0
    risk_pct: float = 1.0
    max_position_pct: float = 25.0
    lot_size: float = 1.0


@dataclass(frozen=True)
class RiskSettings:
    atr_period: int = 14
    atr_mult: float = 2.0
    targets_r: tuple[float, ...] = (2.0, 3.0)


@dataclass(frozen=True)
class ScanSettings:
    fresh_bars: int = 3
    min_score: float = 1.0
    benchmark: str = "SPY"
    edge_horizon: int = 10
    min_bars: int = 60


@dataclass(frozen=True)
class ScoringSettings:
    trend_bonus: float = 1.0
    weekly_bonus: float = 1.0
    rs_bonus: float = 1.0
    rs_strong_pct: float = 80.0
    family_weights: dict[str, float] = field(default_factory=_default_family_weights)
    signal_weights: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestSettings:
    period: str = "10y"
    commission_pct: float = 0.1
    slippage_pct: float = 0.05
    target_r: float = 2.0
    max_hold_bars: int = 20
    bars_per_year: int = 252


@dataclass(frozen=True)
class Settings:
    data: DataSettings = field(default_factory=DataSettings)
    account: AccountSettings = field(default_factory=AccountSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    scan: ScanSettings = field(default_factory=ScanSettings)
    scoring: ScoringSettings = field(default_factory=ScoringSettings)
    backtest: BacktestSettings = field(default_factory=BacktestSettings)


_SECTIONS: dict[str, type] = {
    "data": DataSettings,
    "account": AccountSettings,
    "risk": RiskSettings,
    "scan": ScanSettings,
    "scoring": ScoringSettings,
    "backtest": BacktestSettings,
}


def load_settings(path: Path | None) -> Settings:
    """Load settings from `path`; a missing file yields the defaults."""
    if path is None or not path.is_file():
        return Settings()
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    return settings_from_dict(raw)


def settings_from_dict(raw: dict[str, Any]) -> Settings:
    unknown = set(raw) - set(_SECTIONS)
    if unknown:
        raise ValueError(f"Unknown config sections: {', '.join(sorted(unknown))}")
    return Settings(**{name: _build_section(name, cls, raw.get(name, {})) for name, cls in _SECTIONS.items()})


def _build_section(name: str, cls: type, values: dict[str, Any]) -> Any:
    known = {item.name for item in fields(cls)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"Unknown keys in [{name}]: {', '.join(sorted(unknown))}")
    converted = {key: tuple(value) if isinstance(value, list) else value for key, value in values.items()}
    return cls(**converted)
