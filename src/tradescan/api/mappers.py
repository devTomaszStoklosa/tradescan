"""Map domain results to API response models."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import fields

import pandas as pd

from tradescan.api import schemas
from tradescan.backtest.base import BacktestConfig, Trade
from tradescan.backtest.edge import EdgeStats
from tradescan.backtest.filters import EntryFilter
from tradescan.backtest.metrics import Metrics
from tradescan.backtest.monte_carlo import Distribution, MonteCarlo, PathStats, Percentiles
from tradescan.backtest.oos import Split
from tradescan.backtest.pooled import PooledTrades, Spread
from tradescan.backtest.portfolio_metrics import PortfolioMetrics, TickerContribution
from tradescan.backtest.priority import PriorityRule
from tradescan.backtest.rotation import Targets
from tradescan.backtest.rotation_metrics import RotationMetrics
from tradescan.backtest.rules import Rule
from tradescan.backtest.tickers import PeriodRun
from tradescan.backtest.trade_rules import TradeRules
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.config import SettingsSection
from tradescan.data.schema import bar_dates
from tradescan.journal import JournalTrade, summarize
from tradescan.params import ParamSpec, parameters_of
from tradescan.regime import MarketRegime
from tradescan.scanner import ScanHit
from tradescan.scoring import Scorer
from tradescan.services import (
    BacktestReport,
    ChartData,
    EdgeReport,
    MarketReport,
    PortfolioReport,
    RotationReport,
    ScanInputs,
    ScanReport,
    SweepReport,
    SweptParameter,
    WalkForwardReport,
    WatchlistBacktestReport,
    WindowPick,
)
from tradescan.signals.base import Signal
from tradescan.storage.runs import PinnedRun
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
    return [
        schemas.Point(time=day(date), value=float(value))
        for date, value in zip(bar_dates(clean), clean.to_numpy(), strict=True)
    ]


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
        default=_value(spec.default),
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


def filter_rule_out(rule: type[EntryFilter]) -> schemas.FilterRuleOut:
    return schemas.FilterRuleOut(**rule_out(rule).model_dump(), needs_benchmark=rule.needs_benchmark)


def priority_rule_out(rule: type[PriorityRule]) -> schemas.PriorityRuleOut:
    return schemas.PriorityRuleOut(**rule_out(rule).model_dump(), needs_scan=rule.needs_scan)


def applied_rule_out(rule: Rule) -> schemas.AppliedRuleOut:
    return schemas.AppliedRuleOut(
        name=rule.name, label=rule.label, description=rule.describe(), params=signal_params(rule)
    )


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
        adds=[schemas.FillOut(date=day(fill.date), price=fill.price) for fill in trade.adds],
    )


def percentiles_out(percentiles: Percentiles) -> schemas.PercentilesOut:
    return schemas.PercentilesOut(
        **{item.name: finite(getattr(percentiles, item.name)) for item in fields(percentiles)}
    )


def path_out(path: PathStats) -> schemas.MonteCarloPathOut:
    return schemas.MonteCarloPathOut(
        final_return_pct=finite(path.final_return_pct),
        max_drawdown_pct=finite(path.max_drawdown_pct),
        longest_losing_streak=path.longest_losing_streak,
    )


def distribution_out(distribution: Distribution) -> schemas.MonteCarloMethodOut:
    method = distribution.method
    return schemas.MonteCarloMethodOut(
        name=method.name,
        label=method.label,
        description=method.description,
        final_return_pct=percentiles_out(distribution.final_return_pct),
        max_drawdown_pct=percentiles_out(distribution.max_drawdown_pct),
        longest_losing_streak=percentiles_out(distribution.longest_losing_streak),
        ruin_pct=distribution.ruin_pct,
    )


def monte_carlo_out(monte_carlo: MonteCarlo) -> schemas.MonteCarloOut:
    config = monte_carlo.config
    return schemas.MonteCarloOut(
        simulations=config.simulations,
        ruin_drawdown_pct=config.ruin_drawdown_pct,
        seed=config.seed,
        risk_pct=monte_carlo.risk_pct,
        trades=monte_carlo.trades,
        actual=path_out(monte_carlo.actual),
        methods=[distribution_out(distribution) for distribution in monte_carlo.methods],
    )


def _setup_out(
    ticker: str, signal: Signal, config: BacktestConfig, rules: TradeRules, benchmark: str | None, close: pd.Series
) -> dict[str, object]:
    """The fields a backtest and a sweep share: what was tested, on which data, with which rules."""
    return {
        "ticker": ticker,
        "start": day(close.index[0]),
        "end": day(close.index[-1]),
        **_rules_out(signal, config, rules, benchmark),
    }


def _rules_out(signal: Signal, config: BacktestConfig, rules: TradeRules, benchmark: str | None) -> dict[str, object]:
    """What was tested apart from the ticker: the signal, the settings and the rules."""
    return {
        "signal": signal.name,
        "direction": signal.direction,
        "description": signal.describe(),
        "params": signal_params(signal),
        "config": schemas.BacktestConfigOut(**{item.name: getattr(config, item.name) for item in fields(config)}),
        "entry": applied_rule_out(rules.entry),
        "exits": [applied_rule_out(rule) for rule in rules.exits],
        "filters": [applied_rule_out(rule) for rule in rules.filters],
        "benchmark": benchmark,
    }


def split_out(split: Split) -> schemas.SplitOut:
    return schemas.SplitOut(
        oos_pct=split.oos_pct,
        in_sample_start=day(split.in_sample[0]),
        in_sample_end=day(split.in_sample[1]),
        out_of_sample_start=day(split.out_of_sample[0]),
        out_of_sample_end=day(split.out_of_sample[1]),
    )


def backtest_out(report: BacktestReport) -> schemas.BacktestOut:
    close = report.close
    buy_hold = close / close.iloc[0] * report.config.initial_equity
    return schemas.BacktestOut(
        **_setup_out(report.ticker, report.signal, report.config, report.rules, report.benchmark, close),
        split=split_out(report.split) if report.split else None,
        buy_hold=points(buy_hold),
        runs=[
            schemas.EngineRunOut(
                engine=run.result.engine,
                metrics=metrics_out(run.metrics),
                in_sample=metrics_out(run.periods.in_sample) if run.periods else None,
                out_of_sample=metrics_out(run.periods.out_of_sample) if run.periods else None,
                monte_carlo=monte_carlo_out(run.monte_carlo) if run.monte_carlo else None,
                equity=points(run.result.equity),
                trades=[trade_out(trade) for trade in run.result.trades],
            )
            for run in report.runs
        ],
    )


def sweep_out(report: SweepReport) -> schemas.SweepOut:
    base = report.base
    return schemas.SweepOut(
        **_setup_out(report.ticker, base.signal, base.config, base.rules, base.benchmark, report.close),
        engine=VectorizedEngine.name,
        split=split_out(report.split),
        axes=_axes_out(report.parameters),
        cells=[
            schemas.SweepCellOut(
                values=list(cell.values),
                in_sample=metrics_out(cell.periods.in_sample) if cell.periods else None,
                out_of_sample=metrics_out(cell.periods.out_of_sample) if cell.periods else None,
                error=cell.error,
            )
            for cell in report.cells
        ],
    )


def _axes_out(parameters: tuple[SweptParameter, ...]) -> list[schemas.SweepAxisOut]:
    return [
        schemas.SweepAxisOut(
            target=item.axis.target,
            owner=item.axis.owner or None,
            name=item.axis.name,
            key=item.axis.key,
            label=item.spec.label,
            unit=item.spec.unit,
            kind=item.spec.kind,
            current=item.spec.default,
            values=list(item.axis.values),
        )
        for item in parameters
    ]


def _pick_fields(report: WalkForwardReport, pick: WindowPick) -> dict[str, object]:
    """What an in-sample window picked, as the fields `WindowPickOut` and `WalkForwardWindowOut` share."""
    index = report.close.index
    return {
        "in_sample_start": day(index[pick.span.start]),
        "in_sample_end": day(index[pick.span.end - 1]),
        "values": list(report.combinations[pick.combination].values) if pick.combination is not None else None,
        "qualified": pick.qualified,
        "in_sample": metrics_out(pick.in_sample) if pick.in_sample else None,
    }


def walk_forward_out(report: WalkForwardReport) -> schemas.WalkForwardOut:
    base, plan, index = report.base, report.plan, report.close.index
    start = plan.start
    close = report.close.iloc[start:]
    first = plan.windows[0]
    windows = []
    for item in report.windows:
        segment = item.segment
        windows.append(
            schemas.WalkForwardWindowOut(
                **_pick_fields(report, item.pick),
                out_of_sample_start=day(index[item.window.out_of_sample.start]),
                out_of_sample_end=day(index[item.window.out_of_sample.end - 1]),
                traded_from=day(index[segment.start]) if segment.traded else None,
                traded_to=day(index[segment.end]) if segment.traded else None,
                out_of_sample=metrics_out(item.out_of_sample) if item.out_of_sample else None,
            )
        )
    return schemas.WalkForwardOut(
        **_setup_out(report.ticker, base.signal, base.config, base.rules, base.benchmark, report.close),
        engine=VectorizedEngine.name,
        scheme=plan.scheme,
        metric=report.metric,
        walk_forward=schemas.WalkForwardSettingsOut(
            windows=report.settings.windows,
            in_sample_ratio=report.settings.in_sample_ratio,
            min_trades=report.settings.min_trades,
            in_sample_bars=first.in_sample.bars,
            out_of_sample_bars=first.out_of_sample.bars,
        ),
        axes=_axes_out(report.parameters),
        combinations=len(report.combinations),
        errors=[
            schemas.CombinationErrorOut(values=list(item.values), error=item.error)
            for item in report.combinations
            if item.error is not None
        ],
        out_of_sample_start=day(index[start]),
        windows=windows,
        next=schemas.WindowPickOut(**_pick_fields(report, report.next_pick)),
        metrics=metrics_out(report.metrics),
        unchanged=metrics_out(report.unchanged_metrics),
        efficiency=finite(report.efficiency),
        equity=points(report.stitched.equity),
        unchanged_equity=points(report.unchanged.equity.iloc[start:]),
        buy_hold=points(close / close.iloc[0] * base.config.initial_equity),
        trades=[trade_out(trade) for trade in report.stitched.trades],
    )


def pooled_trades_out(pooled: PooledTrades) -> schemas.PooledTradesOut:
    return schemas.PooledTradesOut(
        trades=pooled.trades,
        win_rate_pct=finite(pooled.win_rate_pct),
        expectancy_r=finite(pooled.expectancy_r),
        profit_factor_r=finite(pooled.profit_factor_r),
        profit_factor_infinite=math.isinf(pooled.profit_factor_r),
        sqn=finite(pooled.sqn),
    )


def spread_out(metric: str, spread: Spread) -> schemas.MetricSpreadOut:
    return schemas.MetricSpreadOut(
        metric=metric,
        tickers=spread.tickers,
        median=finite(spread.median),
        p25=finite(spread.p25),
        p75=finite(spread.p75),
        minimum=finite(spread.minimum),
        maximum=finite(spread.maximum),
        above_break_even_pct=finite(spread.above_break_even_pct),
    )


def watchlist_backtest_out(report: WatchlistBacktestReport) -> schemas.WatchlistBacktestOut:
    base = report.base

    def metrics(run: PeriodRun | None) -> schemas.MetricsOut | None:
        return metrics_out(run.metrics) if run else None

    return schemas.WatchlistBacktestOut(
        **_rules_out(base.signal, base.config, base.rules, base.benchmark),
        universe=report.universe.name,
        engine=VectorizedEngine.name,
        rows=[
            schemas.TickerRunOut(
                ticker=row.ticker,
                start=day(row.start),
                end=day(row.end),
                split=split_out(row.run.split) if row.run.split else None,
                metrics=metrics_out(row.run.full.metrics),
                in_sample=metrics(row.run.in_sample),
                out_of_sample=metrics(row.run.out_of_sample),
            )
            for row in report.rows
        ],
        periods=[
            schemas.PeriodSummaryOut(
                period=period,
                tickers=summary.tickers,
                pooled=pooled_trades_out(summary.pooled),
                spread=[spread_out(metric, value) for metric, value in summary.spreads.items()],
            )
            for period, summary in report.periods.items()
        ],
        missing=report.missing,
    )


def portfolio_period_out(period: PortfolioMetrics) -> schemas.PortfolioPeriodOut:
    stats = period.stats
    return schemas.PortfolioPeriodOut(
        metrics=metrics_out(period.metrics),
        stats=schemas.PortfolioStatsOut(
            average_positions=finite(stats.average_positions),
            max_positions=stats.max_positions,
            average_exposure_pct=finite(stats.average_exposure_pct),
            max_exposure_pct=finite(stats.max_exposure_pct),
            orders=stats.orders,
            skipped_no_slot=stats.skipped_no_slot,
            skipped_no_room=stats.skipped_no_room,
        ),
    )


def contribution_out(row: TickerContribution) -> schemas.TickerContributionOut:
    return schemas.TickerContributionOut(
        ticker=row.ticker,
        trades=row.trades,
        pnl=row.pnl,
        contribution_pct=finite(row.contribution_pct),
        win_rate_pct=finite(row.win_rate_pct),
        expectancy_r=finite(row.expectancy_r),
    )


def scan_inputs_out(scan: ScanInputs) -> schemas.ScanInputsOut:
    return schemas.ScanInputsOut(
        settings={
            section: {name: _value(value) for name, value in values.items()}
            for section, values in scan.settings.items()
        },
        signal_params={signal.name: signal_params(signal) for signal in scan.signals},
    )


def portfolio_out(report: PortfolioReport) -> schemas.PortfolioOut:
    base = report.base
    close = report.benchmark_close.dropna()
    buy_hold = close / close.iloc[0] * base.config.initial_equity if len(close) else close
    return schemas.PortfolioOut(
        **_rules_out(base.signal, base.config, base.rules, base.benchmark),
        universe=report.universe.name,
        start=day(report.calendar[0]),
        end=day(report.calendar[-1]),
        portfolio=schemas.PortfolioConfigOut(
            max_positions=report.portfolio.max_positions, max_exposure_pct=report.portfolio.max_exposure_pct
        ),
        priority=applied_rule_out(report.priority),
        scan=scan_inputs_out(report.scan) if report.scan else None,
        buy_hold_benchmark=report.benchmark,
        buy_hold=points(buy_hold),
        split=split_out(report.split) if report.split else None,
        runs=[
            schemas.PortfolioRunOut(
                engine=run.result.engine,
                full=portfolio_period_out(run.full),
                in_sample=portfolio_period_out(run.in_sample) if run.in_sample else None,
                out_of_sample=portfolio_period_out(run.out_of_sample) if run.out_of_sample else None,
                equity=points(run.result.equity),
                positions=points(run.result.positions.astype(float)),
                trades=[
                    schemas.PortfolioTradeOut(ticker=item.ticker, **trade_out(item.trade).model_dump())
                    for item in run.result.trades
                ],
                tickers=[contribution_out(row) for row in run.contributions],
            )
            for run in report.runs
        ],
        missing=report.missing,
    )


def rotation_period_out(period: RotationMetrics) -> schemas.RotationPeriodOut:
    stats = period.stats
    return schemas.RotationPeriodOut(
        metrics=metrics_out(period.metrics),
        stats=schemas.RotationStatsOut(
            rebalances=stats.rebalances,
            orders=stats.orders,
            unfilled_orders=stats.unfilled_orders,
            average_holdings=finite(stats.average_holdings),
            max_holdings=stats.max_holdings,
            average_exposure_pct=finite(stats.average_exposure_pct),
            average_safe_pct=finite(stats.average_safe_pct),
            average_cash_pct=finite(stats.average_cash_pct),
            turnover_pct=finite(stats.turnover_pct),
            commissions=stats.commissions,
        ),
    )


def targets_out(targets: Targets) -> schemas.TargetsOut:
    return schemas.TargetsOut(
        date=day(targets.date),
        picks=[
            schemas.PickOut(
                ticker=pick.ticker,
                score=finite(pick.score),
                momentum_pct=finite(pick.momentum * 100.0),
                weight_pct=pick.weight_pct,
                held=pick.held,
            )
            for pick in targets.picks
        ],
        safe_pct=targets.safe_pct,
        cash_pct=targets.cash_pct,
    )


def rotation_out(report: RotationReport) -> schemas.RotationOut:
    result, config, rotation = report.result, report.config, report.rotation
    close = report.benchmark_close.dropna()
    buy_hold = close / close.iloc[0] * config.initial_equity if len(close) else close
    return schemas.RotationOut(
        universe=report.universe.name,
        engine=result.engine,
        start=day(result.equity.index[0]),
        end=day(result.equity.index[-1]),
        config=schemas.BacktestConfigOut(**{item.name: getattr(config, item.name) for item in fields(config)}),
        rotation=schemas.RotationConfigOut(
            holdings=rotation.holdings,
            absolute_lookback=rotation.absolute_lookback,
            rebalance=rotation.rebalance,
            safe_asset=rotation.safe_asset,
        ),
        ranking=applied_rule_out(report.ranking),
        weighting=applied_rule_out(report.weighting),
        buy_hold_benchmark=report.benchmark,
        buy_hold=points(buy_hold),
        split=split_out(report.split) if report.split else None,
        full=rotation_period_out(report.full),
        in_sample=rotation_period_out(report.in_sample) if report.in_sample else None,
        out_of_sample=rotation_period_out(report.out_of_sample) if report.out_of_sample else None,
        equity=points(result.equity),
        holdings=points(result.holdings.astype(float)),
        targets=targets_out(result.targets),
        trades=[
            schemas.PortfolioTradeOut(ticker=item.ticker, **trade_out(item.trade).model_dump())
            for item in result.trades
        ],
        tickers=[contribution_out(row) for row in report.contributions],
        missing=report.missing,
    )


def chart_out(data: ChartData) -> schemas.ChartOut:
    bars = data.bars
    return schemas.ChartOut(
        ticker=data.ticker,
        candles=[
            schemas.Candle(
                time=day(index), open=row.open, high=row.high, low=row.low, close=row.close, volume=row.volume
            )
            for index, row in zip(bars.index, bars.itertuples(index=False), strict=True)
        ],
        sma_fast=points(data.sma_fast),
        sma_slow=points(data.sma_slow),
        events=[
            schemas.ChartEventOut(time=day(event.date), signal=event.signal, direction=event.direction)
            for event in data.events
        ],
    )


def pinned_run_out(run: PinnedRun) -> schemas.PinnedRunOut:
    return schemas.PinnedRunOut(
        id=run.id,
        slot=run.slot,
        name=run.name,
        hidden=run.hidden,
        pinned_at=run.pinned_at,
        format=run.format,
        snapshot=run.snapshot,
    )


def journal_trade_out(trade: JournalTrade) -> schemas.JournalTradeOut:
    entry = trade.entry
    run = entry.run
    return schemas.JournalTradeOut(
        id=trade.id,
        ticker=entry.ticker,
        direction=entry.direction,
        opened=entry.opened,
        entry_price=entry.entry_price,
        quantity=entry.quantity,
        stop=entry.stop,
        closed=entry.closed,
        exit_price=entry.exit_price,
        fees=entry.fees,
        notes=entry.notes,
        run=schemas.SuggestingRun(format=run.format, snapshot=run.snapshot) if run else None,
        created_at=trade.created_at,
        updated_at=trade.updated_at,
        is_open=entry.is_open,
        risk=finite(entry.risk),
        profit=finite(entry.profit),
        return_pct=finite(entry.return_pct),
        r_multiple=finite(entry.r_multiple),
    )


def journal_out(trades: Sequence[JournalTrade]) -> schemas.JournalOut:
    summary = summarize([trade.entry for trade in trades])
    return schemas.JournalOut(
        trades=[journal_trade_out(trade) for trade in trades],
        summary=schemas.JournalSummaryOut(
            open_trades=summary.open_trades,
            closed_trades=summary.closed_trades,
            win_rate_pct=finite(summary.win_rate_pct),
            average_return_pct=finite(summary.average_return_pct),
            r_trades=summary.r_trades,
            average_r=finite(summary.average_r),
            total_r=finite(summary.total_r),
        ),
    )
