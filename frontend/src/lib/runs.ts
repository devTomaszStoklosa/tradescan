/**
 * Pinned backtest runs: frozen snapshots of one engine's result, kept in the browser for comparison.
 * A pin keeps what was seen; it is never re-run, so new bars do not change it.
 */
import type { AppliedRuleOut, BacktestConfigOut, BacktestOut, Direction, MetricsOut, Point, SplitOut } from "../api/client";
import type { BacktestForm } from "./params";

/** One chart and one table stay legible up to this many runs, and the run palette has as many colours. */
export const MAX_RUNS = 8;

/** The out-of-sample share is missing from runs pinned before out-of-sample results. */
export type RunConfig = Omit<BacktestConfigOut, "oos_pct"> & Partial<Pick<BacktestConfigOut, "oos_pct">>;

/** The in-sample and out-of-sample periods of a run, with their metrics. */
export interface RunSplit extends SplitOut {
  in_sample: MetricsOut;
  out_of_sample: MetricsOut;
}

/** Everything that defines a run and its result. */
export interface RunSnapshot {
  ticker: string;
  signal: string;
  direction: Direction;
  description: string;
  engine: string;
  start: string;
  end: string;
  /** The signal's parameters the run used, as the server reported them. */
  params: Record<string, number | number[]>;
  /** The stop, costs, account and out-of-sample share the run used. */
  config: RunConfig;
  /** The entry rule, the exit rules and the entry filters the run used, with their parameters. */
  entry: AppliedRuleOut;
  exits: AppliedRuleOut[];
  filters: AppliedRuleOut[];
  /** The benchmark the filters compared; null when no filter read one. */
  benchmark: string | null;
  metrics: MetricsOut;
  /** Null for runs pinned before out-of-sample results, or with too short a history to split. */
  split: RunSplit | null;
  equity: Point[];
  /** Reopens the run on the Backtest page. */
  form: BacktestForm;
}

export interface PinnedRun extends RunSnapshot {
  id: string;
  /** Number and colour (1…MAX_RUNS); kept while the run stays pinned. */
  slot: number;
  name: string;
  pinnedAt: string;
  hidden: boolean;
}

export interface MergeResult {
  runs: PinnedRun[];
  added: number;
  /** Runs skipped because the same run is already pinned. */
  duplicates: number;
  /** Runs skipped because MAX_RUNS was reached. */
  overflow: number;
}

/** One engine's run from a backtest result; null when that engine did not run. */
export function snapshotRun(result: BacktestOut, engine: string, form: BacktestForm): RunSnapshot | null {
  const run = result.runs.find((item) => item.engine === engine);
  if (!run) return null;
  return {
    ticker: result.ticker,
    signal: result.signal,
    direction: result.direction,
    description: result.description,
    engine,
    start: result.start,
    end: result.end,
    params: result.params,
    config: result.config,
    entry: result.entry,
    exits: result.exits,
    filters: result.filters,
    benchmark: result.benchmark,
    metrics: run.metrics,
    split: result.split && run.in_sample && run.out_of_sample ? { ...result.split, in_sample: run.in_sample, out_of_sample: run.out_of_sample } : null,
    equity: run.equity,
    form: { ...form, engines: [engine] },
  };
}

const sortedEntries = (record: object) => Object.entries(record).sort(([left], [right]) => left.localeCompare(right));

/** Equal for runs with the same inputs and data range, so the same run is never pinned twice. */
export function runKey(run: RunSnapshot): string {
  const rule = ({ name, params }: AppliedRuleOut) => [name, sortedEntries(params)];
  return JSON.stringify([
    run.ticker,
    run.signal,
    run.engine,
    run.start,
    run.end,
    sortedEntries(run.params),
    sortedEntries(run.config),
    rule(run.entry),
    run.exits.map(rule),
    run.filters.map(rule),
    run.benchmark,
  ]);
}

export function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/** The preferred slot when it is free, otherwise the lowest free one; null when all are taken. */
export function freeSlot(runs: PinnedRun[], preferred?: number): number | null {
  const taken = new Set(runs.map((run) => run.slot));
  if (preferred !== undefined && Number.isInteger(preferred) && preferred >= 1 && preferred <= MAX_RUNS && !taken.has(preferred)) return preferred;
  for (let slot = 1; slot <= MAX_RUNS; slot++) if (!taken.has(slot)) return slot;
  return null;
}

/** A snapshot as a new pinned run; its slot is assigned when it is merged. */
export function toPinnedRun(snapshot: RunSnapshot, now = new Date()): PinnedRun {
  return { ...snapshot, id: newId(), slot: 0, name: `${snapshot.ticker} ${snapshot.signal}`, pinnedAt: now.toISOString(), hidden: false };
}

/**
 * Add runs to the pinned ones, skipping runs already pinned and any beyond MAX_RUNS.
 * An added run keeps its slot and id when they are free, otherwise it gets free ones.
 */
export function mergeRuns(current: PinnedRun[], incoming: PinnedRun[]): MergeResult {
  const runs = [...current];
  const keys = new Set(runs.map(runKey));
  let duplicates = 0;
  let overflow = 0;
  for (const run of incoming) {
    const key = runKey(run);
    if (keys.has(key)) {
      duplicates += 1;
      continue;
    }
    const slot = freeSlot(runs, run.slot);
    if (slot === null) {
      overflow += 1;
      continue;
    }
    const id = runs.some((item) => item.id === run.id) ? newId() : run.id;
    runs.push({ ...run, id, slot });
    keys.add(key);
  }
  return { runs: sortBySlot(runs), added: runs.length - current.length, duplicates, overflow };
}

export const sortBySlot = (runs: PinnedRun[]): PinnedRun[] => [...runs].sort((left, right) => left.slot - right.slot);

/** CSS colour token of a run's slot. */
export const runColorVar = (run: Pick<PinnedRun, "slot">): string => `--run-${run.slot}`;
