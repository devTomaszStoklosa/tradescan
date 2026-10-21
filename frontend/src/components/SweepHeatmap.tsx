/** One period of a sweep as a grid: columns are the first parameter's values, rows the second's. */
import type { CSSProperties } from "react";

import type { SweepAxisOut, SweepCellOut } from "../api/client";
import { MIN_TRADES, type MetricKey } from "../lib/compare";
import { DASH } from "../lib/format";
import { cellMetrics, cellValue, shade, type HeatScale, type Period, type Shade } from "../lib/sweep";
import { METRICS } from "./BacktestResults";

const cx = (...classes: (string | false | null | undefined)[]) => classes.filter(Boolean).join(" ");

const COLOR: Record<Shade["tone"], string> = {
  good: "var(--heat-good)",
  bad: "var(--heat-bad)",
  level: "var(--heat-good)",
};

/** What the heatmap reads of a swept axis, a sweep's or a rotation sweep's. */
export type HeatmapAxis = Pick<SweepAxisOut, "label" | "unit" | "values">;

export const axisTitle = (axis: HeatmapAxis) => (axis.unit ? `${axis.label} (${axis.unit})` : axis.label);

export const formatValue = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 6 });

/** "Oversold level 10, Distance 2": a combination in words. */
export const describeCombination = (axes: HeatmapAxis[], values: number[]) =>
  axes.map((axis, index) => `${axis.label} ${formatValue(values[index] ?? NaN)}`).join(", ");

export function cellText(cell: SweepCellOut, period: Period, metric: MetricKey): string {
  const metrics = cellMetrics(cell, period);
  const format = METRICS.find((item) => item.key === metric)?.format;
  return metrics && format ? format(metrics) : DASH;
}

export function SweepHeatmap({
  title,
  period,
  axes,
  cells,
  metric,
  scale,
  selected,
  best,
  current,
  onSelect,
}: {
  title: string;
  period: Period;
  axes: HeatmapAxis[];
  cells: SweepCellOut[];
  metric: MetricKey;
  scale: HeatScale | null;
  selected: number | null;
  /** The best in-sample cell, marked with a star in both periods. */
  best: number | null;
  /** The setup's own setting, outlined; null when it is not on the grid. */
  current: number | null;
  onSelect: (index: number) => void;
}) {
  const [columnAxis, rowAxis] = axes;
  if (!columnAxis) return null;
  const rows = rowAxis?.values.length ?? 1;
  const metricLabel = METRICS.find((item) => item.key === metric)?.label ?? metric;

  const renderCell = (index: number) => {
    const cell = cells[index];
    if (!cell) return <td key={index} />;
    const metrics = cellMetrics(cell, period);
    const tint = shade(cellValue(cell, period, metric), scale);
    const few = metrics !== null && metrics.trades < MIN_TRADES;
    const what = describeCombination(axes, cell.values);
    const label = cell.error
      ? `${what}: could not run (${cell.error})`
      : `${what}: ${metricLabel} ${cellText(cell, period, metric)}, ${metrics?.trades ?? 0} trades${few ? " (too few to trust)" : ""}`;
    const style = tint
      ? ({ "--cell-color": COLOR[tint.tone], "--cell-strength": tint.strength } as CSSProperties)
      : undefined;
    return (
      <td key={index} className="p-0.5">
        <button
          type="button"
          onClick={() => onSelect(index)}
          aria-pressed={selected === index}
          aria-label={`${label}${index === best ? ", best in-sample" : ""}${index === current ? ", current setting" : ""}`}
          title={label}
          data-few={few || undefined}
          style={style}
          className={cx(
            "sweep-cell num relative flex h-9 w-full min-w-14 items-center justify-center rounded-md px-1.5 text-xs whitespace-nowrap text-fg",
            few && "text-muted",
            index === current && "outline-2 -outline-offset-2 outline-fg/70 outline-dashed",
            selected === index && "ring-2 ring-accent",
          )}
        >
          {index === best && (
            <span aria-hidden className="mr-0.5">
              ★
            </span>
          )}
          {cell.error ? "×" : cellText(cell, period, metric)}
        </button>
      </td>
    );
  };

  return (
    <div className="relative overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-xs">
        <caption className="mb-1 text-left text-sm font-semibold text-fg">{title}</caption>
        <thead>
          <tr>
            <th scope="col" className="px-2 py-1 text-left font-medium text-muted">
              {rowAxis ? `${axisTitle(rowAxis)} ↓ · ${axisTitle(columnAxis)} →` : `${axisTitle(columnAxis)} →`}
            </th>
            {columnAxis.values.map((value) => (
              <th key={value} scope="col" className="num px-1 py-1 text-center font-medium text-muted">
                {formatValue(value)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, row) => (
            <tr key={row}>
              <th scope="row" className="num px-2 py-0.5 text-left font-medium whitespace-nowrap text-muted">
                {rowAxis ? formatValue(rowAxis.values[row] ?? NaN) : metricLabel}
              </th>
              {columnAxis.values.map((_, column) => renderCell(column * rows + row))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The colour scale and the cell markers, shared by both heatmaps. */
export function SweepLegend({ scale, metric }: { scale: HeatScale | null; metric: MetricKey }) {
  const format = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  let ends: [string, string, string] | null = null;
  let gradient = "";
  if (scale?.kind === "diverging") {
    ends = [format(scale.center - scale.extent), format(scale.center), format(scale.center + scale.extent)];
    gradient = "linear-gradient(to right, var(--heat-bad), var(--heat-mid), var(--heat-good))";
  } else if (scale?.kind === "sequential") {
    ends = [format(scale.min), "", format(scale.max)];
    gradient = "linear-gradient(to right, var(--heat-mid), var(--heat-good))";
  }
  const label = METRICS.find((item) => item.key === metric)?.label ?? metric;
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
      {ends && (
        <div className="flex items-center gap-2">
          <span>{label}</span>
          <span className="num">{ends[0]}</span>
          <span aria-hidden className="h-3 w-28 rounded-sm border border-line" style={{ background: gradient }} />
          <span className="num">{ends[2]}</span>
          {ends[1] && <span className="num">(break-even {ends[1]})</span>}
        </div>
      )}
      <span className="flex items-center gap-1.5">
        <span aria-hidden data-few className="sweep-cell inline-block size-3.5 rounded-sm border border-line" />
        fewer than {MIN_TRADES} trades
      </span>
      <span>★ best in-sample</span>
      <span className="flex items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block size-3.5 rounded-sm outline-2 -outline-offset-2 outline-fg/70 outline-dashed"
        />
        current setting
      </span>
      <span>× could not run</span>
    </div>
  );
}
