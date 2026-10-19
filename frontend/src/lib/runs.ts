/**
 * Pinned runs: frozen snapshots of one engine's result, kept in the browser for comparison.
 * A run is a backtest of one ticker or a portfolio of a universe with one shared equity.
 * A pin keeps what was seen; it is never re-run, so new bars do not change it.
 */
import type {
  AppliedRuleOut,
  BacktestConfigOut,
  BacktestOut,
  Direction,
  MetricsOut,
  MonteCarloOut,
  Point,
  PortfolioOut,
  PortfolioStatsOut,
  ScanInputsOut,
  SplitOut,
} from "../api/client";
import { MONTE_CARLO_SETTINGS } from "./monteCarlo";
import type { BacktestForm } from "./params";
import type { PortfolioForm } from "./portfolio";

/** One chart and one table stay legible up to this many runs, and the run palette has as many colours. */
export const MAX_RUNS = 8;

/** The out-of-sample share is missing from runs pinned before out-of-sample results. */
export type RunConfig = Omit<BacktestConfigOut, "oos_pct"> & Partial<Pick<BacktestConfigOut, "oos_pct">>;

/** The in-sample and out-of-sample periods of a run, with their metrics. */
export interface RunSplit extends SplitOut {
  in_sample: MetricsOut;
  out_of_sample: MetricsOut;
}

/** The setup and the result every kind of run has. */
interface RunBase {
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
  /**
   * The Monte Carlo of the run's trades; null for portfolio runs, for runs pinned before Monte Carlo results,
   * or with fewer than two closed trades.
   */
  monteCarlo: MonteCarloOut | null;
  equity: Point[];
}

/** One setup on one ticker. */
export interface BacktestSnapshot extends RunBase {
  kind: "backtest";
  ticker: string;
  /** Reopens the run on the Backtest page. */
  form: BacktestForm;
}

/** Open positions, exposure and skipped signals of a portfolio run; a period is null when the history has no split. */
export interface PortfolioRunStats {
  full: PortfolioStatsOut;
  in_sample: PortfolioStatsOut | null;
  out_of_sample: PortfolioStatsOut | null;
}

/** One setup on every ticker of a universe with one shared equity. */
export interface PortfolioSnapshot extends RunBase {
  kind: "portfolio";
  /** The watchlist's name, or "custom" for typed tickers. */
  universe: string;
  /** Every ticker of the universe that had data, in the universe's order. */
  tickers: string[];
  /** Tickers of the universe without data. */
  missing: string[];
  /** The max positions and the max exposure the run used. */
  portfolio: PortfolioOut["portfolio"];
  /** The rule that ranked the signals when more fired than fit, with its parameters. */
  priority: AppliedRuleOut;
  /**
   * The scanner's settings and the other signals' parameters the priority read; null when it does not read the
   * scanner, or for runs pinned before they were reported.
   */
  scan: ScanInputsOut | null;
  stats: PortfolioRunStats;
  /** Reopens the run on the Portfolio page. */
  form: PortfolioForm;
}

/** Everything that defines a run and its result. */
export type RunSnapshot = BacktestSnapshot | PortfolioSnapshot;

export type RunKind = RunSnapshot["kind"];

interface PinMeta {
  id: string;
  /** Number and colour (1…MAX_RUNS); kept while the run stays pinned. */
  slot: number;
  name: string;
  pinnedAt: string;
  hidden: boolean;
}

export type PinnedBacktestRun = BacktestSnapshot & PinMeta;
export type PinnedPortfolioRun = PortfolioSnapshot & PinMeta;
export type PinnedRun = PinnedBacktestRun | PinnedPortfolioRun;

export interface MergeResult {
  runs: PinnedRun[];
  added: number;
  /** Runs skipped because the same run is already pinned. */
  duplicates: number;
  /** Runs skipped because MAX_RUNS was reached. */
  overflow: number;
}

/** One engine's run from a backtest result; null when that engine did not run. */
export function snapshotRun(result: BacktestOut, engine: string, form: BacktestForm): BacktestSnapshot | null {
  const run = result.runs.find((item) => item.engine === engine);
  if (!run) return null;
  return {
    kind: "backtest",
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
    monteCarlo: run.monte_carlo,
    equity: run.equity,
    form: { ...form, engines: [engine] },
  };
}

/** One engine's run from a portfolio result; null when that engine did not run. Trades, contributions and positions are not kept. */
export function snapshotPortfolioRun(result: PortfolioOut, engine: string, form: PortfolioForm): PortfolioSnapshot | null {
  const run = result.runs.find((item) => item.engine === engine);
  if (!run) return null;
  const periods = result.split && run.in_sample && run.out_of_sample ? { split: result.split, in_sample: run.in_sample, out_of_sample: run.out_of_sample } : null;
  return {
    kind: "portfolio",
    universe: result.universe,
    tickers: run.tickers.map((item) => item.ticker),
    missing: result.missing,
    portfolio: result.portfolio,
    priority: result.priority,
    scan: result.scan,
    stats: { full: run.full.stats, in_sample: periods?.in_sample.stats ?? null, out_of_sample: periods?.out_of_sample.stats ?? null },
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
    metrics: run.full.metrics,
    split: periods && { ...periods.split, in_sample: periods.in_sample.metrics, out_of_sample: periods.out_of_sample.metrics },
    // The portfolio backtest has no Monte Carlo of its trades.
    monteCarlo: null,
    equity: run.equity,
    form: { ...form, engines: [engine] },
  };
}

const sortedEntries = (record: object) => Object.entries(record).sort(([left], [right]) => left.localeCompare(right));

const ruleKey = ({ name, params }: AppliedRuleOut) => [name, sortedEntries(params)];

const scanKey = (scan: ScanInputsOut | null) =>
  scan && [
    sortedEntries(scan.settings).map(([section, values]) => [section, sortedEntries(values)]),
    sortedEntries(scan.signal_params).map(([signal, params]) => [signal, sortedEntries(params)]),
  ];

/** What only one kind of run has; a new kind of run adds its entry here. */
interface KindSpec<S extends RunSnapshot> {
  /** What the run tested: a ticker or a universe. */
  subject: (run: S) => string;
  /** The inputs beyond the shared setup that tell two runs apart. */
  keyParts: (run: S) => unknown[];
}

type SnapshotOf<K extends RunKind> = Extract<RunSnapshot, { kind: K }>;

const KINDS: { [K in RunKind]: KindSpec<SnapshotOf<K>> } = {
  backtest: {
    subject: (run) => run.ticker,
    keyParts: (run) => [run.ticker],
  },
  portfolio: {
    subject: (run) => run.universe,
    // The members are part of the key: a watchlist's file can change between two runs.
    keyParts: (run) => [run.universe, [...run.tickers].sort(), sortedEntries(run.portfolio), ruleKey(run.priority), scanKey(run.scan)],
  },
};

const kindOf = <S extends RunSnapshot>(run: S) => KINDS[run.kind] as unknown as KindSpec<S>;

/** The ticker of a backtest run, the universe of a portfolio run. */
export const runSubject = (run: RunSnapshot): string => kindOf(run).subject(run);

/** Equal for runs with the same inputs and data range, so the same run is never pinned twice. */
export function runKey(run: RunSnapshot): string {
  const { monteCarlo } = run;
  return JSON.stringify([
    run.kind,
    ...kindOf(run).keyParts(run),
    run.signal,
    run.engine,
    run.start,
    run.end,
    sortedEntries(run.params),
    sortedEntries(run.config),
    ruleKey(run.entry),
    run.exits.map(ruleKey),
    run.filters.map(ruleKey),
    run.benchmark,
    monteCarlo && MONTE_CARLO_SETTINGS.map((name) => monteCarlo[name]),
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
export function toPinnedRun<S extends RunSnapshot>(snapshot: S, now = new Date()): S & PinMeta {
  return { ...snapshot, id: newId(), slot: 0, name: `${runSubject(snapshot)} ${snapshot.signal}`, pinnedAt: now.toISOString(), hidden: false };
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

/** The run when it is a backtest of one ticker. */
export const asBacktest = (run: PinnedRun): PinnedBacktestRun | undefined => (run.kind === "backtest" ? run : undefined);

/** The run when it is a portfolio. */
export const asPortfolio = (run: PinnedRun): PinnedPortfolioRun | undefined => (run.kind === "portfolio" ? run : undefined);
