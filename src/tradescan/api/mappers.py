"""Map domain results to API response models."""

from __future__ import annotations

import math
from dataclasses import fields

import pandas as pd

from tradescan.api import schemas
from tradescan.backtest.base import Trade
from tradescan.backtest.edge import EdgeStats
from tradescan.backtest.metrics import Metrics
from tradescan.backtest.rules import Rule
from tradescan.config import SettingsSection
from tradescan.params import ParamSpec, parameters_of
from tradescan.regime import MarketRegime
from tradescan.scanner import ScanHit
from tradescan.scoring import Scorer
from tradescan.services import BacktestReport, ChartData, EdgeReport, MarketReport, ScanReport
from tradescan.signals.base import Signal
from tradescan.watchlist import Watchlist


def finite(value: float | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def day(timestamp: pd.Timestamp) -> str:
    return pd.Timestamp(timestamp).strftime("%Y-%m-%d")


def points(series: pd.Series) -> list[schemas.Point]:
    clean = series.dropna()
    return [schemas.Point(time=day(index), value=float(value)) for index, value in clean.items()]


def _value(value: object) -> object:
    """Tuples become lists and mappings plain dicts, so pydantic can serialize them."""
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def param_spec_out(spec: ParamSpec) -> schemas.ParamSpecOut:
    return schemas.ParamSpecOut(
        name=spec.name,
        kind=spec.kind,
        label=spec.label,
        unit=spec.unit,
        help=spec.help,
        default=_value(spec.default),  # type: ignore[arg-type]
        minimum=spec.minimum,
        maximum=spec.maximum,
        step=spec.step,
        keys=list(spec.keys) if spec.keys is not None else None,
    )


def section_out(section: SettingsSection) -> schemas.SettingsSectionOut:
    return schemas.SettingsSectionOut(
        name=section.name, label=section.label, params=[param_spec_out(spec) for spec in section.parameters]
    )


def signal_params(signal: Signal | Rule) -> dict[str, float | list[float]]:
    """Current parameter values of a signal or rule."""
    return {spec.name: _value(spec.default) for spec in parameters_of(signal)}  # type: ignore[misc]


def rule_out(rule: type[Rule]) -> schemas.RuleOut:
    return schemas.RuleOut(
        name=rule.name,
        label=rule.label,
        description=rule().describe(),
        template=rule.description,
        params=[param_spec_out(spec) for spec in rule.parameters()],
    )


def applied_rule_out(rule: Rule) -> schemas.AppliedRuleOut:
    return schemas.AppliedRuleOut(name=rule.name, label=rule.label, description=rule.describe(), params=signal_params(rule))


def signal_out(signal: Signal, scorer: Scorer) -> schemas.SignalOut:
    return schemas.SignalOut(
        name=signal.name,
        family=signal.family,
        direction=signal.direction,
        weight=scorer.weight(signal),
        description=signal.describe(),
        template=signal.description,
        params=[param_spec_out(spec) for spec in signal.parameters()],
    )


def watchlist_out(watchlist: Watchlist) -> schemas.WatchlistOut:
    return schemas.WatchlistOut(name=watchlist.name, tickers=list(watchlist.tickers), benchmark=watchlist.benchmark)


def regime_out(regime: MarketRegime) -> schemas.RegimeOut:
    return schemas.RegimeOut(
        benchmark=regime.benchmark,
        benchmark_close=finite(regime.benchmark_close),
        benchmark_above_slow=regime.benchmark_above_slow,
        benchmark_fast_above_slow=regime.benchmark_fast_above_slow,
        pct_above_fast=finite(regime.pct_above_fast),
        pct_above_slow=finite(regime.pct_above_slow),
        new_highs=regime.new_highs,
        new_lows=regime.new_lows,
        universe_size=regime.universe_size,
        regime=regime.regime.value,
    )


def edge_stats_out(stats: EdgeStats) -> schemas.EdgeStatsOut:
    return schemas.EdgeStatsOut(
        signal=stats.signal,
        horizon=stats.horizon,
        events=stats.events,
        win_rate=finite(stats.win_rate),
        mean_return=finite(stats.mean_return),
        median_return=finite(stats.median_return),
        baseline_return=finite(stats.baseline_return),
        edge=finite(stats.edge),
    )


def hit_out(hit: ScanHit, scorer: Scorer) -> schemas.HitOut:
    context, risk, score = hit.context, hit.risk, hit.score
    return schemas.HitOut(
        ticker=hit.ticker,
        direction=hit.direction,
        date=day(context.date),
        close=context.close,
        change_pct=finite(context.change_pct),
        atr=finite(context.atr),
        atr_pct=finite(context.atr_pct),
        adx=finite(context.adx),
        daily_trend=context.daily_trend.value,
        weekly_trend=context.weekly_trend.value,
        rs_percentile=finite(hit.rs_percentile),
        fired=[
            schemas.FiredSignalOut(
                name=item.signal.name,
                family=item.signal.family,
                bars_ago=item.bars_ago,
                weight=scorer.weight(item.signal),
            )
            for item in hit.fired
        ],
        score=schemas.ScoreOut(
            total=score.total,
            signals=score.signals,
            trend=score.trend,
            weekly=score.weekly,
            relative_strength=score.relative_strength,
        ),
        risk=schemas.RiskOut(
            entry=risk.entry,
            stop=finite(risk.stop),
            targets=[finite(target) for target in risk.targets],
            risk_per_share=finite(risk.risk_per_share),
            size=risk.size,
            position_value=finite(risk.position_value),
            risk_amount=finite(risk.risk_amount),
        ),
        edge=edge_stats_out(hit.edge) if hit.edge else None,
    )


def scan_out(report: ScanReport) -> schemas.ScanOut:
    return schemas.ScanOut(
        universe=report.universe.name,
        regime=regime_out(report.regime),
        hits=[hit_out(hit, report.scorer) for hit in report.hits],
        missing=report.missing,
        skipped=report.skipped,
        min_score=report.min_score,
        fresh_bars=report.fresh_bars,
        edge_horizon=report.edge_horizon,
    )


def market_out(report: MarketReport) -> schemas.MarketOut:
    return schemas.MarketOut(universe=report.universe.name, regime=regime_out(report.regime), missing=report.missing)


def edge_out(report: EdgeReport) -> schemas.EdgeOut:
    return schemas.EdgeOut(
        universe=report.universe.name,
        horizons=list(report.horizons),
        tickers=report.tickers,
        rows=[
            schemas.EdgeRowOut(
                signal=row.signal.name,
                family=row.signal.family,
                direction=row.signal.direction,
                description=row.signal.describe(),
                stats=[edge_stats_out(stats) for stats in row.stats],
            )
            for row in report.rows
        ],
        missing=report.missing,
    )


def metrics_out(metrics: Metrics) -> schemas.MetricsOut:
    values = {item.name: getattr(metrics, item.name) for item in fields(metrics)}
    floats = {name: finite(value) for name, value in values.items() if name != "trades"}
    return schemas.MetricsOut(
        **floats,
        trades=metrics.trades,
        profit_factor_infinite=math.isinf(metrics.profit_factor),
    )


def trade_out(trade: Trade) -> schemas.TradeOut:
    return schemas.TradeOut(
        direction=trade.direction,
        signal_date=day(trade.signal_date),
        entry_date=day(trade.entry_date),
        exit_date=day(trade.exit_date),
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        size=trade.size,
        pnl=trade.pnl,
        r_multiple=finite(trade.r_multiple),
        exit_reason=trade.exit_reason,
    )


def backtest_out(report: BacktestReport) -> schemas.BacktestOut:
    config = report.config
    close = report.close
    buy_hold = close / close.iloc[0] * config.initial_equity
    return schemas.BacktestOut(
        ticker=report.ticker,
        signal=report.signal.name,
        direction=report.signal.direction,
        description=report.signal.describe(),
        params=signal_params(report.signal),
        start=day(close.index[0]),
        end=day(close.index[-1]),
        config=schemas.BacktestConfigOut(
            initial_equity=config.initial_equity,
            risk_pct=config.risk_pct,
            max_position_pct=config.max_position_pct,
            lot_size=config.lot_size,
            atr_period=config.atr_period,
            atr_mult=config.atr_mult,
            commission_pct=config.commission_pct,
            slippage_pct=config.slippage_pct,
            bars_per_year=config.bars_per_year,
        ),
        entry=applied_rule_out(report.rules.entry),
        exits=[applied_rule_out(rule) for rule in report.rules.exits],
        buy_hold=points(buy_hold),
        runs=[
            schemas.EngineRunOut(
                engine=run.result.engine,
                metrics=metrics_out(run.metrics),
                equity=points(run.result.equity),
                trades=[trade_out(trade) for trade in run.result.trades],
            )
            for run in report.runs
        ],
    )


def chart_out(data: ChartData) -> schemas.ChartOut:
    bars = data.bars
    return schemas.ChartOut(
        ticker=data.ticker,
        candles=[
            schemas.Candle(time=day(index), open=row.open, high=row.high, low=row.low, close=row.close, volume=row.volume)
            for index, row in zip(bars.index, bars.itertuples(index=False))
        ],
        sma_fast=points(data.sma_fast),
        sma_slow=points(data.sma_slow),
        events=[
            schemas.ChartEventOut(time=day(event.date), signal=event.signal, direction=event.direction)
            for event in data.events
        ],
    )
