/**
 * The results of a sweep or a rotation sweep: both periods as heatmaps of a metric, a summary of them and the picked
 * combination's metrics. Each page adds its own header, the link that opens a combination and what else it shows
 * of one.
 */
import { useMemo, type ReactNode } from "react";

import type { SplitOut, SweepCellOut } from "../api/client";
import { MIN_TRADES, type MetricKey } from "../lib/compare";
import { DASH, fmtNumber, fmtPct } from "../lib/format";
import {
  aboveBreakEven,
  bestCell,
  cellValue,
  heatScale,
  median,
  neighbourAverage,
  periodValues,
  type Period,
} from "../lib/sweep";
import { useResettableState } from "../lib/useResettableState";
import { METRICS, MetricsTable } from "./BacktestResults";
import { cellText, describeCombination, SweepHeatmap, SweepLegend, type HeatmapAxis } from "./SweepHeatmap";
import { Field, Notice, Panel, Select, StatTile } from "./ui";

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** A swept axis with the setup's own value. */
export interface SweptAxis extends HeatmapAxis {
  current: number;
}

function sameValues(left: number[], right: number[]): boolean {
  return (
    left.length === right.length &&
    left.every((value, index) => Math.abs(value - (right[index] ?? NaN)) <= 1e-9 * Math.max(1, Math.abs(value)))
  );
}

export function SweepResults<Cell extends SweepCellOut>({
  split,
  axes,
  cells,
  metric,
  onMetric,
  open,
  details,
}: {
  split: SplitOut;
  axes: SweptAxis[];
  /** Every combination; the first axis changes slowest. */
  cells: Cell[];
  metric: MetricKey;
  onMetric: (metric: MetricKey) => void;
  /** The link that opens the picked combination on its own page; null for none. */
  open: (cell: Cell) => ReactNode;
  /** What else to show of the picked combination below its metrics, e.g. a rotation's stats. */
  details?: (cell: Cell) => ReactNode;
}) {
  const counts = axes.map((axis) => axis.values.length);
  const scale = useMemo(() => heatScale(cells, metric), [cells, metric]);
  const best = useMemo(() => bestCell(cells, metric), [cells, metric]);
  const current = useMemo(() => {
    const index = cells.findIndex((cell) =>
      sameValues(
        cell.values,
        axes.map((axis) => axis.current),
      ),
    );
    return index < 0 ? null : index;
  }, [cells, axes]);
  // A new sweep starts on its best cell; a new metric keeps the pick.
  const [selected, setSelected] = useResettableState<number | null>(best, cells);

  const metricLabel = METRICS.find((item) => item.key === metric)?.label ?? metric;
  const errors = cells.filter((cell) => cell.error);
  const bestOut = best === null ? undefined : cells[best];
  const value = (target: SweepCellOut | undefined, period: Period) =>
    target ? cellText(target, period, metric) : DASH;
  const medianText = (period: Period) => {
    const middle = median(periodValues(cells, period, metric));
    return middle === null ? DASH : fmtNumber(middle);
  };
  const share = aboveBreakEven(cells, "out_of_sample", metric);
  const cell = selected === null ? undefined : cells[selected];

  return (
    <>
      {errors.length > 0 && (
        <Notice>
          {plural(errors.length, "combination")} could not run, e.g. {errors[0]?.error}
        </Notice>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Colour by">
          <Select value={metric} onChange={(event) => onMetric(event.target.value as MetricKey)}>
            {METRICS.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <StatTile
          label={`Best in-sample ${metricLabel}`}
          value={value(bestOut, "in_sample")}
          sub={bestOut && describeCombination(axes, bestOut.values)}
        />
        <StatTile
          label="Same setting out-of-sample"
          value={value(bestOut, "out_of_sample")}
          sub={bestOut && `${bestOut.out_of_sample?.trades ?? 0} trades`}
        />
        <StatTile
          label={`Median ${metricLabel}`}
          value={`${medianText("in_sample")} → ${medianText("out_of_sample")}`}
          sub="in-sample → out-of-sample"
        />
        <StatTile
          label="Above break-even out-of-sample"
          value={share === null ? DASH : fmtPct(share * 100, 0)}
          sub={share === null ? `${metricLabel} has no break-even` : "of the combinations"}
        />
      </div>
      <Panel className="space-y-4">
        <div className="grid gap-4 xl:grid-cols-2">
          {(["in_sample", "out_of_sample"] as const).map((period) => (
            <SweepHeatmap
              key={period}
              title={
                period === "in_sample"
                  ? `In-sample ${split.in_sample_start} → ${split.in_sample_end}`
                  : `Out-of-sample (last ${split.oos_pct}%) ${split.out_of_sample_start} → ${split.out_of_sample_end}`
              }
              period={period}
              axes={axes}
              cells={cells}
              metric={metric}
              scale={scale}
              selected={selected}
              best={best}
              current={current}
              onSelect={setSelected}
            />
          ))}
        </div>
        <SweepLegend scale={scale} metric={metric} />
      </Panel>
      {cell && selected !== null && (
        <section className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">{describeCombination(axes, cell.values)}</h2>
            {open(cell)}
          </div>
          {cell.error ? (
            <Notice>This combination could not run: {cell.error}</Notice>
          ) : (
            <>
              <p className="text-xs text-muted">
                Neighbouring settings average {metricLabel}{" "}
                {(["in_sample", "out_of_sample"] as const)
                  .map((period) => {
                    const average = neighbourAverage(cells, selected, counts, period, metric);
                    const own = cellValue(cell, period, metric);
                    return `${period === "in_sample" ? "in-sample" : "out-of-sample"} ${average === null ? DASH : fmtNumber(average)} (this cell ${own === null ? DASH : fmtNumber(own)})`;
                  })
                  .join(", ")}
                . A result that only one cell reaches is likely luck.
              </p>
              <MetricsTable
                caption="Metrics of the selected combination in both periods"
                columns={[
                  { key: "in", header: "In-sample", metrics: cell.in_sample },
                  { key: "out", header: "Out-of-sample", metrics: cell.out_of_sample },
                ]}
              />
              {details?.(cell)}
              {(["in_sample", "out_of_sample"] as const).map((period) => {
                const trades = cell[period]?.trades ?? 0;
                return trades < MIN_TRADES ? (
                  <p key={period} className="text-xs text-warn">
                    {period === "in_sample" ? "In-sample" : "Out-of-sample"}: only {trades} trades, too few to trust the
                    metrics.
                  </p>
                ) : null;
              })}
            </>
          )}
        </section>
      )}
    </>
  );
}
