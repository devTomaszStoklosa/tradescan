/**
 * Comparison of pinned runs: which parameters differ and which run is best on each metric.
 * Labels and units come from the API's parameter specs, so parameters added later appear without frontend changes.
 */
import type { MetricsOut, ParamSpecOut, Point, SettingsSectionOut, SignalOut } from "../api/client";
import { DASH } from "./format";
import type { RuleSpecs } from "./rules";
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
type Params = Record<string, number | number[]>;

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
 * Rows for parameters that belong to an owner (a signal or a rule), keyed by owner so two owners' "period"
 * never share a row. `paramsOf` is undefined for runs that do not use the owner.
 */
function ownedRows(
  prefix: string,
  owners: Iterable<string>,
  labelOf: (owner: string) => string,
  specsOf: (owner: string) => ParamSpecOut[],
  paramsOf: (run: PinnedRun, owner: string) => Params | undefined,
  runs: PinnedRun[],
): ParamRow[] {
  const rows: ParamRow[] = [];
  for (const owner of owners) {
    const params = runs.map((run) => paramsOf(run, owner));
    for (const name of keysOf(params.filter((item) => item !== undefined))) {
      const spec = specsOf(owner).find((item) => item.name === name);
      rows.push(row(`${prefix}.${owner}.${name}`, `${labelOf(owner)} · ${spec?.label ?? humanize(name)}`, spec?.unit ?? "", params.map((item) => item?.[name])));
    }
  }
  return rows;
}

/**
 * Every input of the runs as rows: what was tested, the data range, the stop, costs and account,
 * the entry and exit rules with their parameters, and the signal parameters.
 */
export function parameterRows(
  runs: PinnedRun[],
  sections: SettingsSectionOut[] = [],
  signals: SignalOut[] = [],
  rules: RuleSpecs = { entry_rules: [], exit_rules: [] },
): ParamRow[] {
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

  const entryLabels = new Map(runs.map((run) => [run.entry.name, run.entry.label]));
  rows.push(row("entry", "Entry", "", runs.map((run) => run.entry.label)));
  rows.push(
    ...ownedRows(
      "entry",
      entryLabels.keys(),
      (name) => entryLabels.get(name) ?? name,
      (name) => rules.entry_rules.find((rule) => rule.name === name)?.params ?? [],
      (run, name) => (run.entry.name === name ? run.entry.params : undefined),
      runs,
    ),
  );
  const exitLabels = new Map(runs.flatMap((run) => run.exits.map((exit) => [exit.name, exit.label] as const)));
  rows.push(row("exits", "Exits", "", runs.map((run) => run.exits.map((exit) => exit.label).join(", ") || "stop only")));
  rows.push(
    ...ownedRows(
      "exit",
      exitLabels.keys(),
      (name) => exitLabels.get(name) ?? name,
      (name) => rules.exit_rules.find((rule) => rule.name === name)?.params ?? [],
      (run, name) => run.exits.find((exit) => exit.name === name)?.params,
      runs,
    ),
  );

  rows.push(
    ...ownedRows(
      "params",
      new Set(runs.map((run) => run.signal)),
      (signal) => signal,
      (signal) => signals.find((item) => item.name === signal)?.params ?? [],
      (run, signal) => (run.signal === signal ? run.params : undefined),
      runs,
    ),
  );
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
