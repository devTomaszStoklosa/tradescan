/**
 * Comparison of pinned runs: which parameters differ and which run is best on each metric.
 * Labels and units come from the API's parameter specs, so parameters added later appear without frontend changes.
 */
import type { MetricsOut, Point, SettingsSectionOut, SignalOut } from "../api/client";
import { DASH } from "./format";
import type { PinnedRun } from "./runs";

/** Fewer trades than this make a run's metrics mostly noise. */
export const MIN_TRADES = 20;

export type MetricKey = Exclude<keyof MetricsOut, "profit_factor_infinite">;

export interface ParamRow {
  key: string;
  label: string;
  unit: string;
  /** Formatted value per run, in the order of the runs given. */
  values: string[];
  differs: boolean;
}

type Raw = number | number[] | string | undefined;

function humanize(name: string): string {
  const words = name.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function display(value: Raw): string {
  if (value === undefined) return DASH;
  if (typeof value === "number") return value.toLocaleString("en-US", { maximumFractionDigits: 6 });
  if (Array.isArray(value)) return value.map((item) => display(item)).join(", ");
  return value;
}

function row(key: string, label: string, unit: string, raw: Raw[]): ParamRow {
  const distinct = new Set(raw.map((value) => JSON.stringify(value ?? null)));
  return { key, label, unit, values: raw.map(display), differs: distinct.size > 1 };
}

/** Keys of all records, in first-seen order. */
const keysOf = (records: object[]): string[] => [...new Set(records.flatMap((record) => Object.keys(record)))];

/**
 * Every input of the runs as rows: what was tested, the data range, the trade rules and account,
 * and the signal parameters. Signal parameters are keyed by signal, so two signals' "period" never share a row.
 */
export function parameterRows(runs: PinnedRun[], sections: SettingsSectionOut[] = [], signals: SignalOut[] = []): ParamRow[] {
  const settingSpecs = sections.flatMap((section) => section.params);
  const rows: ParamRow[] = [
    row("ticker", "Ticker", "", runs.map((run) => run.ticker)),
    row("signal", "Signal", "", runs.map((run) => run.signal)),
    row("engine", "Engine", "", runs.map((run) => run.engine)),
    row("data", "Data", "", runs.map((run) => `${run.start} → ${run.end}`)),
  ];
  for (const name of keysOf(runs.map((run) => run.config))) {
    const spec = settingSpecs.find((item) => item.name === name);
    const values = runs.map((run) => (run.config as unknown as Record<string, number | undefined>)[name]);
    rows.push(row(`config.${name}`, spec?.label ?? humanize(name), spec?.unit ?? "", values));
  }
  for (const signal of new Set(runs.map((run) => run.signal))) {
    const specs = signals.find((item) => item.name === signal)?.params ?? [];
    const params = runs.map((run) => (run.signal === signal ? run.params : undefined));
    for (const name of keysOf(params.filter((item) => item !== undefined))) {
      const spec = specs.find((item) => item.name === name);
      rows.push(row(`params.${signal}.${name}`, `${signal} · ${spec?.label ?? humanize(name)}`, spec?.unit ?? "", params.map((item) => item?.[name])));
    }
  }
  return rows;
}

/** A metric as a number for ranking; an infinite profit factor ranks above every finite one. */
export function metricValue(metrics: MetricsOut, key: MetricKey): number | null {
  if (key === "profit_factor" && metrics.profit_factor_infinite) return Infinity;
  const value = metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Positions holding the highest value; empty unless at least two values exist and they differ. */
export function bestIndexes(values: (number | null)[]): Set<number> {
  const present = values.filter((value): value is number => value !== null);
  if (present.length < 2) return new Set();
  const best = Math.max(...present);
  if (present.every((value) => value === best)) return new Set();
  return new Set(values.flatMap((value, index) => (value === best ? [index] : [])));
}

/** Equity as % return since the first point, so runs with different capital share one scale. */
export function returnCurve(points: Point[]): Point[] {
  const first = points[0]?.value;
  if (!first) return [];
  return points.map((point) => ({ time: point.time, value: (point.value / first - 1) * 100 }));
}
