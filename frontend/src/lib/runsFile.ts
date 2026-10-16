/**
 * Pinned runs on disk. Browser storage and the JSON export use the same format:
 * `{version, runs}`, with each equity curve as two arrays (dates, values rounded to cents),
 * about half the size of one object per point. Older files are upgraded when read: version 1 is from
 * before entry and exit rules, version 2 from before out-of-sample results, version 3 from before entry filters.
 */
import type { AppliedRuleOut, MetricsOut } from "../api/client";
import { formatTemplate, type Overrides } from "./overrides";
import { moveLegacyExitSettings } from "./rules";
import { MAX_RUNS, type PinnedRun } from "./runs";

export const RUNS_FILE_VERSION = 4;

interface StoredEquity {
  time: string[];
  value: number[];
}

type StoredRun = Omit<PinnedRun, "equity"> & { equity: StoredEquity };

export interface RunsFile {
  version: number;
  runs: StoredRun[];
}

export function encodeRuns(runs: PinnedRun[]): RunsFile {
  return {
    version: RUNS_FILE_VERSION,
    runs: runs.map(({ equity, ...run }) => ({
      ...run,
      equity: { time: equity.map((point) => point.time), value: equity.map((point) => Math.round(point.value * 100) / 100) },
    })),
  };
}

// --- Validation: an imported file or edited storage must not break the page ------------------------

type Check = (value: unknown) => boolean;

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const text: Check = (value) => typeof value === "string";
const finite: Check = (value) => typeof value === "number" && Number.isFinite(value);
const flag: Check = (value) => typeof value === "boolean";
const arrayOf = (check: Check): Check => (value) => Array.isArray(value) && value.every(check);
const recordOf = (check: Check): Check => (value) => isRecord(value) && Object.values(value).every(check);
const oneOf = (...checks: Check[]): Check => (value) => checks.some((check) => check(value));

const paramValue = oneOf(finite, arrayOf(finite), recordOf(finite));

const equity: Check = (value) => isRecord(value) && arrayOf(text)(value.time) && arrayOf(finite)(value.value) && (value.time as unknown[]).length === (value.value as unknown[]).length;

const metrics: Check = (value) => recordOf(oneOf(finite, flag, (item) => item === null))(value) && finite((value as Partial<MetricsOut>).trades);

const form: Check = (value) =>
  isRecord(value) &&
  text(value.ticker) &&
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

const split: Check = (value) =>
  isRecord(value) &&
  finite(value.oos_pct) &&
  ["in_sample_start", "in_sample_end", "out_of_sample_start", "out_of_sample_end"].every((key) => text(value[key])) &&
  metrics(value.in_sample) &&
  metrics(value.out_of_sample);

const appliedRule: Check = (value) =>
  isRecord(value) && text(value.name) && text(value.label) && text(value.description) && recordOf(oneOf(finite, arrayOf(finite)))(value.params);

const RUN_FIELDS: Record<keyof StoredRun, Check> = {
  id: text,
  slot: (value) => Number.isInteger(value) && (value as number) >= 1 && (value as number) <= MAX_RUNS,
  name: text,
  pinnedAt: text,
  hidden: flag,
  ticker: text,
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
  equity,
  form,
};

function decodeRun(value: unknown, index: number): PinnedRun {
  if (!isRecord(value)) throw new Error(`Run ${index + 1} is not an object`);
  for (const [field, check] of Object.entries(RUN_FIELDS)) {
    if (!check(value[field])) throw new Error(`Run ${index + 1} has an invalid "${field}"`);
  }
  // Only known fields are kept, so nothing unexpected reaches storage again.
  const run = Object.fromEntries(Object.keys(RUN_FIELDS).map((field) => [field, value[field]])) as StoredRun;
  const points = run.equity.time.map((time, at) => ({ time, value: run.equity.value[at] as number }));
  return { ...run, equity: points };
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
    rule("target", "Profit target", "Limit order {target_r:g}R from the entry reference", { target_r: target_r as number }),
    rule("time", "Time exit", "Exit at the open {max_hold_bars} bars after the entry bar", { max_hold_bars: max_hold_bars as number }),
  ];
  const moved = moveLegacyExitSettings((isRecord(value.form.settings) ? value.form.settings : {}) as Overrides, {});
  return {
    ...value,
    config,
    entry: rule("next_open", "Next open", "Market order at the next open; stop and target are measured from the signal bar's close", {}),
    exits,
    form: { ...value.form, settings: moved.settings, entry: "next_open", entryParams: {}, exits: ["target", "time"], exitParams: moved.exitParams },
  };
}

// --- Version 2: runs had no out-of-sample results, and cannot get them without a rerun --------------

const upgradeV2 = (value: unknown): unknown => (isRecord(value) ? { ...value, split: null } : value);

// --- Version 3: runs had no entry filters, so a signal always traded and no benchmark was compared --

const upgradeV3 = (value: unknown): unknown =>
  isRecord(value) && isRecord(value.form)
    ? { ...value, filters: [], benchmark: null, form: { ...value.form, filters: [], filterParams: {}, benchmark: "" } }
    : value;

const UPGRADES: Record<number, (value: unknown) => unknown> = {
  1: (value) => upgradeV3(upgradeV2(upgradeV1(value))),
  2: (value) => upgradeV3(upgradeV2(value)),
  3: upgradeV3,
  [RUNS_FILE_VERSION]: (value) => value,
};

/** Runs from parsed JSON; throws an Error naming the first problem. */
export function decodeRuns(data: unknown): PinnedRun[] {
  if (!isRecord(data) || !Array.isArray(data.runs)) throw new Error("This is not a tradescan runs file");
  const upgrade = typeof data.version === "number" ? UPGRADES[data.version] : undefined;
  if (!upgrade) throw new Error(`Unsupported runs file version: ${String(data.version)}`);
  return data.runs.map((run, index) => decodeRun(upgrade(run), index));
}

export function parseRunsFile(content: string): PinnedRun[] {
  let data: unknown;
  try {
    data = JSON.parse(content);
  } catch {
    throw new Error("The file is not valid JSON");
  }
  return decodeRuns(data);
}
