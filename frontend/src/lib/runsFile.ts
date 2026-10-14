/**
 * Pinned runs on disk. Browser storage and the JSON export use the same format:
 * `{version, runs}`, with each equity curve as two arrays (dates, values rounded to cents),
 * about half the size of one object per point.
 */
import type { MetricsOut } from "../api/client";
import { MAX_RUNS, type PinnedRun } from "./runs";

export const RUNS_FILE_VERSION = 1;

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
  recordOf(paramValue)(value.signalParams);

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
  metrics,
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

/** Runs from parsed JSON; throws an Error naming the first problem. */
export function decodeRuns(data: unknown): PinnedRun[] {
  if (!isRecord(data) || !Array.isArray(data.runs)) throw new Error("This is not a tradescan runs file");
  if (data.version !== RUNS_FILE_VERSION) throw new Error(`Unsupported runs file version: ${String(data.version)}`);
  return data.runs.map(decodeRun);
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
