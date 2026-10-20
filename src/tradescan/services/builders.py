"""Builders that turn settings into the collaborators the use cases need."""

from __future__ import annotations

from collections.abc import Mapping

from tradescan.backtest.allocation import PortfolioConfig
from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.monte_carlo import MonteCarloConfig
from tradescan.backtest.rotation import Rebalance, RotationConfig
from tradescan.config import Settings
from tradescan.context import ContextBuilder
from tradescan.params import GroupOverrides, check_group
from tradescan.regime import MarketRegimeAnalyzer
from tradescan.risk import RiskPlanner
from tradescan.scoring import Scorer
from tradescan.signals.registry import SignalRegistry


def build_scorer(settings: Settings) -> Scorer:
    scoring = settings.scoring
    return Scorer(
        family_weights=scoring.family_weights,
        signal_weights=scoring.signal_weights,
        trend_bonus=scoring.trend_bonus,
        weekly_bonus=scoring.weekly_bonus,
        rs_bonus=scoring.rs_bonus,
        rs_strong_pct=scoring.rs_strong_pct,
    )


def build_context_builder(settings: Settings) -> ContextBuilder:
    trend = settings.trend
    return ContextBuilder(
        atr_period=settings.risk.atr_period,
        fast_period=trend.fast_period,
        slow_period=trend.slow_period,
        weekly_period=trend.weekly_period,
        rs_periods=trend.rs_periods,
        rs_weights=trend.rs_weights,
    )


def build_regime_analyzer(settings: Settings) -> MarketRegimeAnalyzer:
    regime = settings.regime
    return MarketRegimeAnalyzer(
        fast_period=regime.fast_period,
        slow_period=regime.slow_period,
        high_low_period=regime.high_low_period,
        risk_on_breadth=regime.risk_on_breadth,
        risk_off_breadth=regime.risk_off_breadth,
    )


def build_risk_planner(settings: Settings) -> RiskPlanner:
    account, risk = settings.account, settings.risk
    return RiskPlanner(
        equity=account.equity,
        risk_pct=account.risk_pct,
        max_position_pct=account.max_position_pct,
        atr_mult=risk.atr_mult,
        targets_r=risk.targets_r,
        lot_size=account.lot_size,
    )


def build_backtest_config(settings: Settings) -> BacktestConfig:
    account, backtest, risk, pyramid = settings.account, settings.backtest, settings.risk, settings.pyramid
    return BacktestConfig(
        initial_equity=account.equity,
        risk_pct=account.risk_pct,
        max_position_pct=account.max_position_pct,
        lot_size=account.lot_size,
        atr_period=risk.atr_period,
        atr_mult=risk.atr_mult,
        commission_pct=backtest.commission_pct,
        slippage_pct=backtest.slippage_pct,
        bars_per_year=backtest.bars_per_year,
        oos_pct=backtest.oos_pct,
        max_units=pyramid.max_units,
        add_every_atr=pyramid.add_every_atr,
    )


def build_monte_carlo_config(settings: Settings) -> MonteCarloConfig:
    monte_carlo = settings.monte_carlo
    return MonteCarloConfig(
        simulations=monte_carlo.simulations, ruin_drawdown_pct=monte_carlo.ruin_drawdown_pct, seed=monte_carlo.seed
    )


def build_portfolio_config(settings: Settings) -> PortfolioConfig:
    portfolio = settings.portfolio
    return PortfolioConfig(max_positions=portfolio.max_positions, max_exposure_pct=portfolio.max_exposure_pct)


def build_rotation_config(settings: Settings, rebalance: Rebalance, safe_asset: str | None) -> RotationConfig:
    rotation = settings.rotation
    return RotationConfig(
        holdings=rotation.holdings,
        absolute_lookback=rotation.absolute_lookback,
        rebalance=rebalance,
        safe_asset=safe_asset,
    )


def resolve_settings(settings: Settings, overrides: GroupOverrides, registry: SignalRegistry) -> Settings:
    """The configured settings plus one run's overrides; per-signal weights must name known signals."""
    weights = (overrides.get("scoring") or {}).get("signal_weights") or {}
    if isinstance(weights, Mapping):
        check_group(weights, registry.names(), "signal weight(s)")
    return settings.with_overrides(overrides)
