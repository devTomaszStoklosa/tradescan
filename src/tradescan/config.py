"""Application settings loaded from a TOML file.

Every section and key is optional; anything missing falls back to the defaults below.
Unknown keys raise an error so typos in the config file do not go unnoticed.

Settings that change a result are declared with `param`, so a single run can override them
(`Settings.with_overrides`) and the web UI can offer them. Paths and names are not parameters and
cannot be overridden.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, ClassVar

from tradescan.params import GroupOverrides, ParamSpec, check_group, param, parameters_of, validate, with_overrides
from tradescan.signals.base import Family

_FAMILY_WEIGHTS = {
    "trend": 1.0,
    "momentum": 1.0,
    "breakout": 1.5,
    "mean_reversion": 1.0,
    "volume": 1.0,
    "pattern": 0.5,
}


@dataclass(frozen=True)
class DataSettings:
    label: ClassVar[str] = "Data"
    period: str = "5y"
    interval: str = "1d"
    cache_dir: str = ".cache"
    cache_ttl_hours: float = 12.0


@dataclass(frozen=True)
class AccountSettings:
    label: ClassVar[str] = "Account"
    equity: float = param(100_000.0, minimum=1.0, maximum=1e12, step=1000.0, label="Account equity")
    risk_pct: float = param(1.0, minimum=0.01, maximum=100.0, step=0.1, label="Risk per trade", unit="%")
    max_position_pct: float = param(
        25.0, minimum=0.1, maximum=100.0, step=1.0, label="Max position", unit="% of equity",
        help="Caps a position's value, whatever the stop distance",
    )
    lot_size: float = param(
        1.0, minimum=1e-8, maximum=1e6, step=0.0001, label="Lot size", help="1 for stocks, e.g. 0.0001 for crypto"
    )


@dataclass(frozen=True)
class RiskSettings:
    label: ClassVar[str] = "Risk plan"
    atr_period: int = param(14, minimum=2, maximum=100, step=1, label="ATR period", unit="bars")
    atr_mult: float = param(2.0, minimum=0.25, maximum=20.0, step=0.25, label="Stop distance", unit="ATR")
    targets_r: tuple[float, ...] = param(
        (2.0, 3.0), minimum=0.25, maximum=50.0, step=0.25, label="Scan targets", unit="R",
        help="Profit targets shown in scan results, as multiples of the risk",
    )


@dataclass(frozen=True)
class ScanSettings:
    label: ClassVar[str] = "Scan"
    fresh_bars: int = param(3, minimum=1, maximum=60, step=1, label="Fresh within", unit="bars")
    min_score: float = param(1.0, minimum=-50.0, maximum=100.0, step=0.5, label="Minimum score")
    benchmark: str = "SPY"
    edge_horizon: int = param(10, minimum=1, maximum=250, step=1, label="Edge horizon", unit="bars")
    min_bars: int = param(
        60, minimum=20, maximum=5000, step=1, label="Minimum history", unit="bars", help="Tickers with less are skipped"
    )


@dataclass(frozen=True)
class ScoringSettings:
    label: ClassVar[str] = "Scoring"
    trend_bonus: float = param(
        1.0, minimum=0.0, maximum=10.0, step=0.5, label="Daily trend bonus",
        help="Added when the daily trend agrees, subtracted when it disagrees",
    )
    weekly_bonus: float = param(
        1.0, minimum=0.0, maximum=10.0, step=0.5, label="Weekly trend bonus",
        help="Added when the weekly trend agrees, subtracted when it disagrees",
    )
    rs_bonus: float = param(1.0, minimum=0.0, maximum=10.0, step=0.5, label="Relative strength bonus")
    rs_strong_pct: float = param(
        80.0, minimum=50.0, maximum=100.0, step=1.0, label="Strong RS percentile",
        help="Longs need RS at or above it, shorts at or below 100 minus it",
    )
    family_weights: dict[str, float] = param(
        _FAMILY_WEIGHTS, minimum=-10.0, maximum=10.0, step=0.5, label="Family weights",
        keys=[family.value for family in Family],
    )
    signal_weights: dict[str, float] = param(
        {}, minimum=-10.0, maximum=10.0, step=0.5, label="Signal weights", help="Per-signal overrides of the family weight"
    )


@dataclass(frozen=True)
class TrendSettings:
    label: ClassVar[str] = "Trend & relative strength"
    fast_period: int = param(50, minimum=2, maximum=400, step=1, label="Daily trend: fast SMA", unit="bars")
    slow_period: int = param(200, minimum=3, maximum=500, step=1, label="Daily trend: slow SMA", unit="bars")
    weekly_period: int = param(30, minimum=2, maximum=200, step=1, label="Weekly trend SMA", unit="weeks")
    rs_periods: tuple[int, ...] = param(
        (63, 126, 189, 252), minimum=1, maximum=1000, step=1, label="RS lookbacks", unit="bars",
        help="Returns over these lookbacks are combined into the relative-strength rank",
    )
    rs_weights: tuple[float, ...] = param(
        (0.4, 0.2, 0.2, 0.2), minimum=0.0, maximum=10.0, step=0.05, label="RS weights", help="One weight per lookback"
    )

    def __post_init__(self) -> None:
        if self.fast_period >= self.slow_period:
            raise ValueError(f"trend: fast_period ({self.fast_period}) must be below slow_period ({self.slow_period})")
        if len(self.rs_periods) != len(self.rs_weights):
            raise ValueError(f"trend: {len(self.rs_periods)} RS lookbacks need as many weights, got {len(self.rs_weights)}")


@dataclass(frozen=True)
class RegimeSettings:
    label: ClassVar[str] = "Market regime"
    fast_period: int = param(50, minimum=2, maximum=400, step=1, label="Breadth: fast SMA", unit="bars")
    slow_period: int = param(200, minimum=3, maximum=500, step=1, label="Benchmark and breadth: slow SMA", unit="bars")
    high_low_period: int = param(252, minimum=20, maximum=1000, step=1, label="New highs/lows window", unit="bars")
    risk_on_breadth: float = param(
        60.0, minimum=0.0, maximum=100.0, step=1.0, label="Risk-on breadth", unit="% above fast SMA"
    )
    risk_off_breadth: float = param(
        40.0, minimum=0.0, maximum=100.0, step=1.0, label="Risk-off breadth", unit="% above fast SMA"
    )

    def __post_init__(self) -> None:
        if self.fast_period >= self.slow_period:
            raise ValueError(f"regime: fast_period ({self.fast_period}) must be below slow_period ({self.slow_period})")
        if self.risk_off_breadth > self.risk_on_breadth:
            raise ValueError(
                f"regime: risk_off_breadth ({self.risk_off_breadth:g}) must not exceed risk_on_breadth ({self.risk_on_breadth:g})"
            )


@dataclass(frozen=True)
class BacktestSettings:
    label: ClassVar[str] = "Backtest"
    period: str = "10y"
    commission_pct: float = param(0.1, minimum=0.0, maximum=5.0, step=0.01, label="Commission", unit="%")
    slippage_pct: float = param(0.05, minimum=0.0, maximum=5.0, step=0.01, label="Slippage", unit="%")
    bars_per_year: int = param(
        252, minimum=1, maximum=10_000, step=1, label="Bars per year", help="Annualizes CAGR, Sharpe and Sortino (365 for crypto)"
    )
    oos_pct: float = param(
        30.0, minimum=10.0, maximum=50.0, step=5.0, label="Out-of-sample share", unit="% of history",
        help="The last part of the history, reported separately and left out of tuning",
    )


@dataclass(frozen=True)
class MonteCarloSettings:
    label: ClassVar[str] = "Monte Carlo"
    simulations: int = param(
        1000, minimum=100, maximum=10_000, step=100, label="Simulations", help="Resampled sequences of the run's trades per method"
    )
    ruin_drawdown_pct: float = param(
        50.0, minimum=1.0, maximum=100.0, step=5.0, label="Ruin level", unit="% drawdown",
        help="A drawdown from the peak at least this deep counts as ruin",
    )
    seed: int = param(
        0, minimum=0, maximum=2**31 - 1, step=1, label="Random seed", help="The same seed repeats the same simulations"
    )


@dataclass(frozen=True)
class Settings:
    data: DataSettings = field(default_factory=DataSettings)
    account: AccountSettings = field(default_factory=AccountSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    scan: ScanSettings = field(default_factory=ScanSettings)
    scoring: ScoringSettings = field(default_factory=ScoringSettings)
    trend: TrendSettings = field(default_factory=TrendSettings)
    regime: RegimeSettings = field(default_factory=RegimeSettings)
    backtest: BacktestSettings = field(default_factory=BacktestSettings)
    monte_carlo: MonteCarloSettings = field(default_factory=MonteCarloSettings)

    def with_overrides(self, overrides: GroupOverrides | None) -> Settings:
        """These settings with validated overrides for one run, e.g. {"risk": {"atr_mult": 3}}."""
        if not overrides:
            return self
        check_group(overrides, list(_SECTIONS), "settings section(s)")
        return replace(
            self, **{name: with_overrides(getattr(self, name), values, owner=name) for name, values in overrides.items()}
        )


_SECTIONS: dict[str, type] = {item.name: item.default_factory for item in fields(Settings)}  # type: ignore[misc]


@dataclass(frozen=True)
class SettingsSection:
    name: str
    label: str
    parameters: tuple[ParamSpec, ...]


def adjustable_sections(settings: Settings) -> list[SettingsSection]:
    """Sections with adjustable parameters; each spec's default is the configured value."""
    sections = [
        SettingsSection(name=name, label=getattr(settings, name).label, parameters=parameters_of(getattr(settings, name)))
        for name in _SECTIONS
    ]
    return [section for section in sections if section.parameters]


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
    section = cls(**converted)
    validate(section, owner=f"[{name}]")
    return section
