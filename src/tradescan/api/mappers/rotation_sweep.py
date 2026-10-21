"""Map a rotation sweep report."""

from __future__ import annotations

from tradescan.api.mappers.backtest import applied_rule_out, metrics_out, split_out
from tradescan.api.mappers.common import day
from tradescan.api.mappers.rotation import config_out, rotation_config_out, rotation_period_out
from tradescan.api.schemas.rotation_sweep import RotationSweepAxisOut, RotationSweepCellOut, RotationSweepOut
from tradescan.backtest.rotation import VectorizedRotationEngine
from tradescan.services.rotation_sweep import RotationSweepCell, RotationSweepReport


def _cell_out(cell: RotationSweepCell) -> RotationSweepCellOut:
    periods = cell.periods
    if periods is None:
        return RotationSweepCellOut(
            values=list(cell.values),
            in_sample=None,
            out_of_sample=None,
            in_sample_stats=None,
            out_of_sample_stats=None,
            error=cell.error,
        )
    in_sample, out_of_sample = rotation_period_out(periods.in_sample), rotation_period_out(periods.out_of_sample)
    return RotationSweepCellOut(
        values=list(cell.values),
        in_sample=metrics_out(periods.in_sample.metrics),
        out_of_sample=metrics_out(periods.out_of_sample.metrics),
        in_sample_stats=in_sample.stats,
        out_of_sample_stats=out_of_sample.stats,
        error=cell.error,
    )


def rotation_sweep_out(report: RotationSweepReport) -> RotationSweepOut:
    base = report.base
    return RotationSweepOut(
        universe=report.universe.name,
        engine=VectorizedRotationEngine.name,
        start=day(report.dates[0]),
        end=day(report.dates[-1]),
        config=config_out(base.config),
        rotation=rotation_config_out(base.rotation),
        ranking=applied_rule_out(base.ranking),
        weighting=applied_rule_out(base.weighting),
        buy_hold_benchmark=base.benchmark,
        split=split_out(report.split),
        axes=[
            RotationSweepAxisOut(
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
            for item in report.parameters
        ],
        cells=[_cell_out(cell) for cell in report.cells],
        missing=report.missing,
    )
