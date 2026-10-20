"""Map a sweep report, and the swept axes a walk-forward reports too."""

from __future__ import annotations

from tradescan.api.mappers.backtest import metrics_out, setup_out, split_out
from tradescan.api.schemas.sweep import SweepAxisOut, SweepCellOut, SweepOut
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.services.sweep import SweepReport, SweptParameter


def sweep_out(report: SweepReport) -> SweepOut:
    base = report.base
    return SweepOut(
        **setup_out(report.ticker, base.signal, base.config, base.rules, base.benchmark, report.close),
        engine=VectorizedEngine.name,
        split=split_out(report.split),
        axes=axes_out(report.parameters),
        cells=[
            SweepCellOut(
                values=list(cell.values),
                in_sample=metrics_out(cell.periods.in_sample) if cell.periods else None,
                out_of_sample=metrics_out(cell.periods.out_of_sample) if cell.periods else None,
                error=cell.error,
            )
            for cell in report.cells
        ],
    )


def axes_out(parameters: tuple[SweptParameter, ...]) -> list[SweepAxisOut]:
    return [
        SweepAxisOut(
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
