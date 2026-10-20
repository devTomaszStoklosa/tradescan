"""Map a walk-forward report."""

from __future__ import annotations

from tradescan.api.mappers.backtest import metrics_out, setup_out, trade_out
from tradescan.api.mappers.common import day, finite, points
from tradescan.api.mappers.sweep import axes_out
from tradescan.api.schemas.walk_forward import (
    CombinationErrorOut,
    WalkForwardOut,
    WalkForwardSettingsOut,
    WalkForwardWindowOut,
    WindowPickOut,
)
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.services.walk_forward import WalkForwardReport, WindowPick


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


def walk_forward_out(report: WalkForwardReport) -> WalkForwardOut:
    base, plan, index = report.base, report.plan, report.close.index
    start = plan.start
    close = report.close.iloc[start:]
    first = plan.windows[0]
    windows = []
    for item in report.windows:
        segment = item.segment
        windows.append(
            WalkForwardWindowOut(
                **_pick_fields(report, item.pick),
                out_of_sample_start=day(index[item.window.out_of_sample.start]),
                out_of_sample_end=day(index[item.window.out_of_sample.end - 1]),
                traded_from=day(index[segment.start]) if segment.traded else None,
                traded_to=day(index[segment.end]) if segment.traded else None,
                out_of_sample=metrics_out(item.out_of_sample) if item.out_of_sample else None,
            )
        )
    return WalkForwardOut(
        **setup_out(report.ticker, base.signal, base.config, base.rules, base.benchmark, report.close),
        engine=VectorizedEngine.name,
        scheme=plan.scheme,
        metric=report.metric,
        walk_forward=WalkForwardSettingsOut(
            windows=report.settings.windows,
            in_sample_ratio=report.settings.in_sample_ratio,
            min_trades=report.settings.min_trades,
            in_sample_bars=first.in_sample.bars,
            out_of_sample_bars=first.out_of_sample.bars,
        ),
        axes=axes_out(report.parameters),
        combinations=len(report.combinations),
        errors=[
            CombinationErrorOut(values=list(item.values), error=item.error)
            for item in report.combinations
            if item.error is not None
        ],
        out_of_sample_start=day(index[start]),
        windows=windows,
        next=WindowPickOut(**_pick_fields(report, report.next_pick)),
        metrics=metrics_out(report.metrics),
        unchanged=metrics_out(report.unchanged_metrics),
        efficiency=finite(report.efficiency),
        equity=points(report.stitched.equity),
        unchanged_equity=points(report.unchanged.equity.iloc[start:]),
        buy_hold=points(close / close.iloc[0] * base.config.initial_equity),
        trades=[trade_out(trade) for trade in report.stitched.trades],
    )
