/**
 * Parameter sweep: the form and its URL, the parameters a sweep can change, their value ranges,
 * and the summaries the heatmaps show.
 *
 * A sweep starts from a backtest setup (the same URL keys as the Backtest page) and adds up to two
 * axes: `ax1=signal.oversold&ax1v=5:20:1`. An axis key is `target[.owner].name`, as the API reports it.
 */
import type { ConfigOut, MetricsOut, ParamSpecOut, SignalOut, SweepAxisIn, SweepCellOut, SweepIn, SweepTarget } from "../api/client";
import { BACKTEST_FIELDS, MONTE_CARLO_SECTION, SETUP_SECTIONS } from "./choices";
import { metricValue, type MetricKey } from "./compare";
import { withOwner, withValue, type Values } from "./overrides";
import { readBacktestSetup, setupBody, writeBacktestSetup, type BacktestSetup } from "./params";
import { findRule, type RuleDefaults } from "./rules";

/** Values per axis when a parameter is picked: 9 × 9 = 81 combinations fit well under the cap. */
export const DEFAULT_VALUES = 9;
export const DEFAULT_METRIC: MetricKey = "sharpe";

export interface AxisForm {
  /** `target[.owner].name`, e.g. "exit.target.target_r". */
  key: string;
  from: number | null;
  to: number | null;
  step: number | null;
}

export interface SweepForm extends BacktestSetup {
  axes: AxisForm[];
}

/** A parameter a sweep can change, with its value in the setup. */
export interface SweepParam {
  key: string;
  target: SweepTarget;
  owner: string | null;
  name: string;
  /** What holds it, for grouping the picker, e.g. "Exit: Profit target". */
  group: string;
  spec: ParamSpecOut;
  current: number;
}

const isNumber = (spec: ParamSpecOut) => spec.kind === "int" || spec.kind === "float";

const keyOf = (target: SweepTarget, owner: string | null, name: string) => [target, owner, name].filter(Boolean).join(".");

function paramsOf(target: SweepTarget, owner: string | null, group: string, specs: ParamSpecOut[], values: Values | undefined): SweepParam[] {
  return specs.filter(isNumber).map((spec) => {
    const value = values?.[spec.name];
    return {
      key: keyOf(target, owner, spec.name),
      target,
      owner,
      name: spec.name,
      group,
      spec,
      current: typeof value === "number" ? value : (spec.default as number),
    };
  });
}

/**
 * Every single-number parameter of the setup the Backtest form offers: the signal's, the active filters',
 * the entry rule's, the active exits', the stop's, the costs' and the pyramiding's. The out-of-sample share is left out: it defines
 * the split.
 */
export function sweepParams(setup: BacktestSetup, config: ConfigOut, signals: SignalOut[]): SweepParam[] {
  const result: SweepParam[] = [];
  const signal = signals.find((item) => item.name === setup.signal);
  if (signal) result.push(...paramsOf("signal", null, `Signal: ${signal.name}`, signal.params, setup.signalParams));
  for (const name of setup.filters) {
    const filter = findRule(config.filter_rules, name);
    if (filter) result.push(...paramsOf("filter", filter.name, `Filter: ${filter.label}`, filter.params, setup.filterParams[filter.name]));
  }
  const entry = findRule(config.entry_rules, setup.entry);
  if (entry) result.push(...paramsOf("entry", null, `Entry: ${entry.label}`, entry.params, setup.entryParams));
  for (const name of setup.exits) {
    const exit = findRule(config.exit_rules, name);
    if (exit) result.push(...paramsOf("exit", exit.name, `Exit: ${exit.label}`, exit.params, setup.exitParams[exit.name]));
  }
  const fields: Record<string, readonly string[]> = BACKTEST_FIELDS;
  for (const name of SETUP_SECTIONS) {
    const section = config.sections.find((item) => item.name === name);
    if (!section || !config.sweep.sections.includes(name)) continue;
    const specs = section.params.filter(
      (spec) => (!fields[name] || fields[name].includes(spec.name)) && !config.sweep.fixed.includes(`${name}.${spec.name}`),
    );
    result.push(...paramsOf("settings", name, section.label, specs, setup.settings[name]));
  }
  return result;
}

// --- Value ranges --------------------------------------------------------------------------------

function decimals(value: number): number {
  const [mantissa = "", exponent] = String(value).split("e");
  const places = (mantissa.split(".")[1] ?? "").length - Number(exponent ?? 0);
  return Math.max(0, places);
}

const round = (value: number, places: number) => Number(value.toFixed(Math.min(places, 12)));

/** An axis around the setup's value: DEFAULT_VALUES steps of the declared step, kept inside the declared range. */
export function defaultAxis(param: SweepParam, count = DEFAULT_VALUES): AxisForm {
  const { minimum, maximum, step } = param.spec;
  const places = Math.max(decimals(param.current), decimals(step));
  const half = Math.floor((count - 1) / 2);
  let from = param.current - half * step;
  let to = param.current + (count - 1 - half) * step;
  if (from < minimum) {
    to = Math.min(maximum, to + (minimum - from));
    from = minimum;
  }
  if (to > maximum) {
    from = Math.max(minimum, from - (to - maximum));
    to = maximum;
  }
  return { key: param.key, from: round(from, places), to: round(to, places), step };
}

export type AxisRange = { values: number[]; problem: null } | { values: null; problem: string };

const problem = (text: string): AxisRange => ({ values: null, problem: text });

/** The values From, To and Step give (both ends included), or what is wrong with them. */
export function axisValues(axis: AxisForm, spec: ParamSpecOut, limits: ConfigOut["sweep"]): AxisRange {
  const { from, to, step } = axis;
  if (from === null || to === null || step === null) return problem("Enter From, To and Step");
  if (!(step > 0)) return problem("Step must be above 0");
  if (to < from) return problem("To must not be below From");
  if (from < spec.minimum || to > spec.maximum) return problem(`Allowed: ${spec.minimum}–${spec.maximum}`);
  if (spec.kind === "int" && ![from, to, step].every(Number.isInteger)) return problem("Use whole numbers");
  const count = Math.floor((to - from) / step + 1e-9) + 1;
  if (count < limits.min_values) return problem(`Needs at least ${limits.min_values} values`);
  if (count > limits.max_values) return problem(`${count} values: at most ${limits.max_values}`);
  const places = Math.max(decimals(from), decimals(step));
  return { values: Array.from({ length: count }, (_, index) => round(from + index * step, places)), problem: null };
}

/** Product of the axes' value counts; null while an axis is invalid. */
export function combinations(ranges: AxisRange[]): number | null {
  if (!ranges.length || ranges.some((range) => range.values === null)) return null;
  return ranges.reduce((total, range) => total * (range.values?.length ?? 0), 1);
}

// --- Form, URL and request ----------------------------------------------------------------------

/** A sweep of `setup` with no axes picked yet. */
/** A sweep runs no Monte Carlo, so a backtest's Monte Carlo settings stay behind. */
export function newSweepForm(setup: BacktestSetup): SweepForm {
  const { ticker, signal, period, settings, signalParams, entry, entryParams, exits, exitParams, filters, filterParams, benchmark } = setup;
  const { [MONTE_CARLO_SECTION]: _monteCarlo, ...setupSettings } = settings;
  return { ticker, signal, period, settings: setupSettings, signalParams, entry, entryParams, exits, exitParams, filters, filterParams, benchmark, axes: [] };
}

const number = (text: string | undefined): number | null => {
  if (text === undefined || text.trim() === "") return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
};

export function readSweepForm(params: URLSearchParams, defaults: RuleDefaults): SweepForm {
  const axes: AxisForm[] = [];
  for (const position of [1, 2]) {
    const key = params.get(`ax${position}`);
    if (!key) continue;
    const [from, to, step] = (params.get(`ax${position}v`) ?? "").split(":");
    axes.push({ key, from: number(from), to: number(to), step: number(step) });
  }
  return { ...newSweepForm(readBacktestSetup(params, defaults)), axes };
}

export function writeSweepForm(form: SweepForm, defaults?: RuleDefaults): URLSearchParams {
  const params = writeBacktestSetup(form, defaults);
  form.axes.forEach((axis, index) => {
    params.set(`ax${index + 1}`, axis.key);
    params.set(`ax${index + 1}v`, [axis.from, axis.to, axis.step].map((value) => value ?? "").join(":"));
  });
  return params;
}

/** The sweep request without the account, which the page adds; null until the setup and every axis are valid. */
export function sweepBody(form: SweepForm, params: SweepParam[], limits: ConfigOut["sweep"]): SweepIn | null {
  const setup = setupBody(form);
  if (!setup || !form.axes.length || form.axes.length > limits.max_axes) return null;
  const axes: SweepAxisIn[] = [];
  const ranges: AxisRange[] = [];
  for (const axis of form.axes) {
    const param = params.find((item) => item.key === axis.key);
    if (!param) return null;
    const range = axisValues(axis, param.spec, limits);
    if (range.values === null) return null;
    ranges.push(range);
    axes.push({ target: param.target, owner: param.owner, name: param.name, values: range.values });
  }
  const count = combinations(ranges);
  if (count === null || count > limits.max_combinations) return null;
  return { ...setup, axes };
}

/** Where the setup keeps the values of parameters that belong to an owner, by sweep target. */
const GROUPS: Partial<Record<SweepTarget, "exitParams" | "filterParams">> = { exit: "exitParams", filter: "filterParams" };

/** The setup with one combination's values, e.g. to open it on the Backtest page. */
export function withCombination(setup: BacktestSetup, params: SweepParam[], values: number[]): BacktestSetup {
  let next = setup;
  params.forEach((param, index) => {
    const value = values[index];
    if (value === undefined) return;
    if (param.target === "signal") next = { ...next, signalParams: withValue(next.signalParams, param.spec, value) };
    else if (param.target === "entry") next = { ...next, entryParams: withValue(next.entryParams, param.spec, value) };
    else {
      const owner = param.owner ?? "";
      const group = GROUPS[param.target] ?? "settings";
      next = { ...next, [group]: withOwner(next[group], owner, withValue(next[group][owner] ?? {}, param.spec, value)) };
    }
  });
  return next;
}

// --- Results ----------------------------------------------------------------------------------

export type Period = "in_sample" | "out_of_sample";


/** Break-even per metric: values above it are good, below it bad. Metrics without one use a one-hue scale. */
export const BREAK_EVEN: Partial<Record<MetricKey, number>> = {
  total_return_pct: 0,
  cagr_pct: 0,
  sharpe: 0,
  sortino: 0,
  expectancy_r: 0,
  sqn: 0,
  profit_factor: 1,
};

export const cellMetrics = (cell: SweepCellOut, period: Period): MetricsOut | null => cell[period];

export function cellValue(cell: SweepCellOut, period: Period, metric: MetricKey): number | null {
  const metrics = cellMetrics(cell, period);
  return metrics ? metricValue(metrics, metric) : null;
}

export type HeatScale = { kind: "diverging"; center: number; extent: number } | { kind: "sequential"; min: number; max: number };

/** One scale for both periods, so the same colour means the same value in each heatmap. */
export function heatScale(cells: SweepCellOut[], metric: MetricKey): HeatScale | null {
  const values = cells.flatMap((cell) => [cellValue(cell, "in_sample", metric), cellValue(cell, "out_of_sample", metric)]);
  const finite = values.filter((value): value is number => value !== null && Number.isFinite(value));
  const center = BREAK_EVEN[metric];
  if (center !== undefined) {
    const extent = Math.max(0, ...finite.map((value) => Math.abs(value - center)));
    return { kind: "diverging", center, extent };
  }
  if (!finite.length) return null;
  return { kind: "sequential", min: Math.min(...finite), max: Math.max(...finite) };
}

export interface Shade {
  /** "good" and "bad" are the two arms of a diverging scale; "level" is the one-hue scale. */
  tone: "good" | "bad" | "level";
  /** 0 (neutral) to 1 (the strongest colour). */
  strength: number;
}

export function shade(value: number | null, scale: HeatScale | null): Shade | null {
  if (value === null || scale === null) return null;
  if (scale.kind === "diverging") {
    const offset = value - scale.center;
    const strength = !Number.isFinite(offset) ? 1 : scale.extent > 0 ? Math.min(1, Math.abs(offset) / scale.extent) : 0;
    return { tone: offset >= 0 ? "good" : "bad", strength };
  }
  const span = scale.max - scale.min;
  const strength = !Number.isFinite(value) ? 1 : span > 0 ? (value - scale.min) / span : 0.5;
  return { tone: "level", strength: Math.min(1, Math.max(0, strength)) };
}

/** Position of the highest value in a period; ties go to the first. Null when no cell has a value. */
export function bestCell(cells: SweepCellOut[], metric: MetricKey, period: Period = "in_sample"): number | null {
  let best: number | null = null;
  cells.forEach((cell, index) => {
    const value = cellValue(cell, period, metric);
    if (value === null) return;
    const current = best === null ? null : cellValue(cells[best]!, period, metric);
    if (current === null || value > current) best = index;
  });
  return best;
}

export function median(values: number[]): number | null {
  const sorted = values.filter(Number.isFinite).sort((left, right) => left - right);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle]! : (sorted[middle - 1]! + sorted[middle]!) / 2;
}

export const periodValues = (cells: SweepCellOut[], period: Period, metric: MetricKey): number[] =>
  cells.flatMap((cell) => cellValue(cell, period, metric) ?? []);

/** Share of the cells with a value above break-even; null for metrics without one. */
export function aboveBreakEven(cells: SweepCellOut[], period: Period, metric: MetricKey): number | null {
  const center = BREAK_EVEN[metric];
  const values = periodValues(cells, period, metric);
  if (center === undefined || !values.length) return null;
  return values.filter((value) => value > center).length / values.length;
}

/** Positions of the cells next to `index` (diagonals included) in a grid whose first axis changes slowest. */
export function neighbours(index: number, counts: number[]): number[] {
  const columns = counts[0] ?? 0;
  const rows = counts[1] ?? 1;
  const column = Math.floor(index / rows);
  const row = index % rows;
  const result: number[] = [];
  for (let dc = -1; dc <= 1; dc++) {
    for (let dr = -1; dr <= 1; dr++) {
      const c = column + dc;
      const r = row + dr;
      if ((dc || dr) && c >= 0 && c < columns && r >= 0 && r < rows) result.push(c * rows + r);
    }
  }
  return result;
}

/** Mean of the neighbours' finite values: whether a cell's result holds for nearby settings. */
export function neighbourAverage(cells: SweepCellOut[], index: number, counts: number[], period: Period, metric: MetricKey): number | null {
  const values = neighbours(index, counts)
    .map((position) => cellValue(cells[position]!, period, metric))
    .filter((value): value is number => value !== null && Number.isFinite(value));
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
}
