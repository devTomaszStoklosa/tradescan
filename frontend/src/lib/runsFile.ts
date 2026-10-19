/**
 * Pinned runs on disk. The JSON export is `{version, runs}`, with each equity curve as two arrays (dates, values
 * rounded to cents), about half the size of one object per point. The server keeps each run in the same format,
 * with the version it was written in: the pin (id, slot, name, hidden, pinned time) in its own fields and the rest
 * as the snapshot; a journal trade keeps the whole run that suggested it, pin included, as its snapshot.
 * Older runs are upgraded when read: version 1 is from
 * before entry and exit rules, version 2 from before out-of-sample results, version 3 from before entry filters,
 * version 4 from before Monte Carlo results, version 5 from before portfolio runs, version 6 from before the score
 * priority's signal parameters, version 7 from before portfolio results reported what the score read of the scanner.
 */
import type { AppliedRuleOut, MetricsOut, PinnedRunIn, PinnedRunOut, SuggestingRun } from "../api/client";
import { formatTemplate, type Overrides } from "./overrides";
import { moveLegacyExitSettings } from "./rules";
import { MAX_RUNS, type PinnedBacktestRun, type PinnedPortfolioRun, type PinnedRun, type RunKind } from "./runs";

export const RUNS_FILE_VERSION = 8;

interface StoredEquity {
  time: string[];
  value: number[];
}

type Stored<R> = Omit<R, "equity"> & { equity: StoredEquity };
type StoredRun = Stored<PinnedBacktestRun> | Stored<PinnedPortfolioRun>;

export interface RunsFile {
  version: number;
  runs: StoredRun[];
}

export function encodeRun({ equity, ...run }: PinnedRun): StoredRun {
  return {
    ...run,
    equity: {
      time: equity.map((point) => point.time),
      value: equity.map((point) => Math.round(point.value * 100) / 100),
    },
  } as StoredRun;
}

export function encodeRuns(runs: PinnedRun[]): RunsFile {
  return { version: RUNS_FILE_VERSION, runs: runs.map(encodeRun) };
}

/** A pinned run as the server keeps it. */
export function runRecord(run: PinnedRun): PinnedRunIn {
  const { id, slot, name, hidden, pinnedAt, ...snapshot } = encodeRun(run);
  return { id, slot, name, hidden, pinned_at: pinnedAt, format: RUNS_FILE_VERSION, snapshot };
}

/** A copy of a pinned run for the journal trade it suggested. */
export const suggestingRun = (run: PinnedRun): SuggestingRun => ({
  format: RUNS_FILE_VERSION,
  snapshot: { ...encodeRun(run) },
});

// --- Validation: an imported file or edited storage must not break the page ------------------------

type Check = (value: unknown) => boolean;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const text: Check = (value) => typeof value === "string";
const finite: Check = (value) => typeof value === "number" && Number.isFinite(value);
const flag: Check = (value) => typeof value === "boolean";
const arrayOf =
  (check: Check): Check =>
  (value) =>
    Array.isArray(value) && value.every(check);
const recordOf =
  (check: Check): Check =>
  (value) =>
    isRecord(value) && Object.values(value).every(check);
const oneOf =
  (...checks: Check[]): Check =>
  (value) =>
    checks.some((check) => check(value));

const paramValue = oneOf(finite, arrayOf(finite), recordOf(finite));

const equity: Check = (value) =>
  isRecord(value) &&
  arrayOf(text)(value.time) &&
  arrayOf(finite)(value.value) &&
  (value.time as unknown[]).length === (value.value as unknown[]).length;

const metrics: Check = (value) =>
  recordOf(oneOf(finite, flag, (item) => item === null))(value) && finite((value as Partial<MetricsOut>).trades);

/** The setup both pages' forms share. */
const setupForm: Check = (value) =>
  isRecord(value) &&
  text(value.signal) &&
  arrayOf(text)(value.engines) &&
  text(value.period) &&
  recordOf(recordOf(paramValue))(value.settings) &&
  recordOf(paramValue)(value.signalParams) &&
  text(value.entry) &&
  recordOf(paramValue)(value.entryParams) &&
  arrayOf(text)(value.exits) &&
  recordOf(recordOf(paramValue))(value.exitParams) &&
  arrayOf(text)(value.filters) &&
  recordOf(recordOf(paramValue))(value.filterParams) &&
  text(value.benchmark);

const backtestForm: Check = (value) => setupForm(value) && text((value as Record<string, unknown>).ticker);

const universe: Check = (value) => isRecord(value) && text(value.watchlist) && text(value.tickers);

const portfolioForm: Check = (value) =>
  setupForm(value) &&
  isRecord(value) &&
  universe(value.universe) &&
  text(value.priority) &&
  recordOf(paramValue)(value.priorityParams) &&
  recordOf(recordOf(paramValue))(value.scoreSignalParams);

const split: Check = (value) =>
  isRecord(value) &&
  finite(value.oos_pct) &&
  ["in_sample_start", "in_sample_end", "out_of_sample_start", "out_of_sample_end"].every((key) => text(value[key])) &&
  metrics(value.in_sample) &&
  metrics(value.out_of_sample);

const optionalNumber = oneOf(finite, (value) => value === null);

const percentiles: Check = (value) =>
  isRecord(value) && ["p5", "p25", "p50", "p75", "p95"].every((key) => optionalNumber(value[key]));

const monteCarloMethod: Check = (value) =>
  isRecord(value) &&
  text(value.name) &&
  text(value.label) &&
  text(value.description) &&
  percentiles(value.final_return_pct) &&
  percentiles(value.max_drawdown_pct) &&
  percentiles(value.longest_losing_streak) &&
  finite(value.ruin_pct);

const monteCarlo: Check = (value) =>
  isRecord(value) &&
  ["simulations", "ruin_drawdown_pct", "seed", "risk_pct", "trades"].every((key) => finite(value[key])) &&
  isRecord(value.actual) &&
  optionalNumber(value.actual.final_return_pct) &&
  optionalNumber(value.actual.max_drawdown_pct) &&
  finite(value.actual.longest_losing_streak) &&
  arrayOf(monteCarloMethod)(value.methods);

const appliedRule: Check = (value) =>
  isRecord(value) &&
  text(value.name) &&
  text(value.label) &&
  text(value.description) &&
  recordOf(oneOf(finite, arrayOf(finite)))(value.params);

const portfolioSettings: Check = (value) =>
  isRecord(value) && finite(value.max_positions) && finite(value.max_exposure_pct);

const scanInputs: Check = (value) =>
  isRecord(value) &&
  recordOf(recordOf(paramValue))(value.settings) &&
  recordOf(recordOf(oneOf(finite, arrayOf(finite))))(value.signal_params);

const portfolioStats: Check = (value) =>
  isRecord(value) &&
  ["average_positions", "average_exposure_pct", "max_exposure_pct"].every((key) => optionalNumber(value[key])) &&
  ["max_positions", "orders", "skipped_no_slot", "skipped_no_room"].every((key) => finite(value[key]));

const optionalStats = oneOf((value) => value === null, portfolioStats);

const periodStats: Check = (value) =>
  isRecord(value) && portfolioStats(value.full) && optionalStats(value.in_sample) && optionalStats(value.out_of_sample);

const is =
  (expected: string): Check =>
  (value) =>
    value === expected;

/** Fields every kind of run has; `keyof` of the union is the fields its kinds share. */
type SharedField = Exclude<keyof StoredRun, "kind" | "form">;

const SHARED_FIELDS: Record<SharedField, Check> = {
  id: text,
  slot: (value) => Number.isInteger(value) && (value as number) >= 1 && (value as number) <= MAX_RUNS,
  name: text,
  pinnedAt: text,
  hidden: flag,
  signal: text,
  direction: (value) => value === "long" || value === "short",
  description: text,
  engine: text,
  start: text,
  end: text,
  params: recordOf(oneOf(finite, arrayOf(finite))),
  config: recordOf(finite),
  entry: appliedRule,
  exits: arrayOf(appliedRule),
  filters: arrayOf(appliedRule),
  benchmark: oneOf((value) => value === null, text),
  metrics,
  split: oneOf((value) => value === null, split),
  monteCarlo: oneOf((value) => value === null, monteCarlo),
  equity,
};

/** Fields only one kind of run has; a new kind of run adds its entry here. */
const KIND_FIELDS: { [K in RunKind]: Record<Exclude<keyof Extract<StoredRun, { kind: K }>, SharedField>, Check> } = {
  backtest: { kind: is("backtest"), ticker: text, form: backtestForm },
  portfolio: {
    kind: is("portfolio"),
    universe: text,
    tickers: arrayOf(text),
    missing: arrayOf(text),
    portfolio: portfolioSettings,
    priority: appliedRule,
    scan: oneOf((value) => value === null, scanInputs),
    stats: periodStats,
    form: portfolioForm,
  },
};

function decodeRun(value: unknown, index: number): PinnedRun {
  if (!isRecord(value)) throw new Error(`Run ${index + 1} is not an object`);
  const kind =
    typeof value.kind === "string" && Object.hasOwn(KIND_FIELDS, value.kind) ? (value.kind as RunKind) : null;
  if (!kind) throw new Error(`Run ${index + 1} has an invalid "kind"`);
  const fields: Record<string, Check> = { ...SHARED_FIELDS, ...KIND_FIELDS[kind] };
  for (const [field, check] of Object.entries(fields)) {
    if (!check(value[field])) throw new Error(`Run ${index + 1} has an invalid "${field}"`);
  }
  // Only known fields are kept, so nothing unexpected reaches storage again.
  const run = Object.fromEntries(Object.keys(fields).map((field) => [field, value[field]])) as StoredRun;
  const points = run.equity.time.map((time, at) => ({ time, value: run.equity.value[at] as number }));
  return { ...run, equity: points } as PinnedRun;
}

// --- Version 1: every run used a next-open entry, a target and a time exit, set in `config` ------------

const rule = (name: string, label: string, template: string, params: Record<string, number>): AppliedRuleOut => ({
  name,
  label,
  description: formatTemplate(template, params),
  params,
});

/** A version 1 run in the current format; anything malformed is left for validation to reject. */
function upgradeV1(value: unknown): unknown {
  if (!isRecord(value) || !isRecord(value.config) || !isRecord(value.form)) return value;
  const { target_r = 2, max_hold_bars = 20, ...config } = value.config;
  if (!finite(target_r) || !finite(max_hold_bars)) return value;
  const exits = [
    rule("target", "Profit target", "Limit order {target_r:g}R from the entry reference", {
      target_r: target_r as number,
    }),
    rule("time", "Time exit", "Exit at the open {max_hold_bars} bars after the entry bar", {
      max_hold_bars: max_hold_bars as number,
    }),
  ];
  const moved = moveLegacyExitSettings((isRecord(value.form.settings) ? value.form.settings : {}) as Overrides, {});
  return {
    ...value,
    config,
    entry: rule(
      "next_open",
      "Next open",
      "Market order at the next open; stop and target are measured from the signal bar's close",
      {},
    ),
    exits,
    form: {
      ...value.form,
      settings: moved.settings,
      entry: "next_open",
      entryParams: {},
      exits: ["target", "time"],
      exitParams: moved.exitParams,
    },
  };
}

// --- Version 2: runs had no out-of-sample results, and cannot get them without a rerun --------------

const upgradeV2 = (value: unknown): unknown => (isRecord(value) ? { ...value, split: null } : value);

// --- Version 3: runs had no entry filters, so a signal always traded and no benchmark was compared --

const upgradeV3 = (value: unknown): unknown =>
  isRecord(value) && isRecord(value.form)
    ? { ...value, filters: [], benchmark: null, form: { ...value.form, filters: [], filterParams: {}, benchmark: "" } }
    : value;

// --- Version 4: runs had no Monte Carlo, and cannot get one without a rerun -------------------------

const upgradeV4 = (value: unknown): unknown => (isRecord(value) ? { ...value, monteCarlo: null } : value);

// --- Version 5: every run was a backtest of one ticker ----------------------------------------------

const upgradeV5 = (value: unknown): unknown => (isRecord(value) ? { ...value, kind: "backtest" } : value);

// --- Version 6: the score priority counted the signals other than the traded one with their defaults ------

const upgradeV6 = (value: unknown): unknown =>
  isRecord(value) && value.kind === "portfolio" && isRecord(value.form)
    ? { ...value, form: { ...value.form, scoreSignalParams: {} } }
    : value;

// --- Version 7: portfolio results did not report what the score read of the scanner -----------------

const upgradeV7 = (value: unknown): unknown =>
  isRecord(value) && value.kind === "portfolio" ? { ...value, scan: null } : value;

const UPGRADES: Record<number, (value: unknown) => unknown> = {
  1: (value) => upgradeV7(upgradeV6(upgradeV5(upgradeV4(upgradeV3(upgradeV2(upgradeV1(value))))))),
  2: (value) => upgradeV7(upgradeV6(upgradeV5(upgradeV4(upgradeV3(upgradeV2(value)))))),
  3: (value) => upgradeV7(upgradeV6(upgradeV5(upgradeV4(upgradeV3(value))))),
  4: (value) => upgradeV7(upgradeV6(upgradeV5(upgradeV4(value)))),
  5: (value) => upgradeV7(upgradeV6(upgradeV5(value))),
  6: (value) => upgradeV7(upgradeV6(value)),
  7: upgradeV7,
  [RUNS_FILE_VERSION]: (value) => value,
};

function upgradeOf(version: unknown): (value: unknown) => unknown {
  const upgrade = typeof version === "number" ? UPGRADES[version] : undefined;
  if (!upgrade) throw new Error(`Unsupported runs file version: ${String(version)}`);
  return upgrade;
}

/** Runs from parsed JSON; throws an Error naming the first problem. */
export function decodeRuns(data: unknown): PinnedRun[] {
  if (!isRecord(data) || !Array.isArray(data.runs)) throw new Error("This is not a tradescan runs file");
  const upgrade = upgradeOf(data.version);
  return data.runs.map((run, index) => decodeRun(upgrade(run), index));
}

/** A run the server keeps; throws an Error naming the first problem. */
export function decodeRunRecord(record: PinnedRunOut, index = 0): PinnedRun {
  const { id, slot, name, hidden, pinned_at: pinnedAt, format, snapshot } = record;
  return decodeRun(upgradeOf(format)({ ...snapshot, id, slot, name, hidden, pinnedAt }), index);
}

/** The run a journal trade keeps; throws an Error naming the first problem. */
export const decodeSuggestingRun = ({ format, snapshot }: SuggestingRun): PinnedRun =>
  decodeRun(upgradeOf(format)(snapshot), 0);

export function parseRunsFile(content: string): PinnedRun[] {
  let data: unknown;
  try {
    data = JSON.parse(content);
  } catch {
    throw new Error("The file is not valid JSON");
  }
  return decodeRuns(data);
}
