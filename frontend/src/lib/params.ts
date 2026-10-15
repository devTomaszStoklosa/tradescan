/**
 * Form state <-> URL search params. Keeping requests in the URL makes results shareable,
 * survives reloads, and lets the query cache show earlier results on back navigation.
 * Parameter overrides travel as `set.<section>.<name>` and `sig.<signal>.<name>`, a backtest's rules as
 * `entry=<rule>`, `exit=<rule>,<rule>` (`none` for no exits) and `en.<rule>.<name>` / `ex.<rule>.<name>` (see overrides.ts).
 */
import type { BacktestIn, BacktestSetupIn, Direction, EdgeIn, Family, ScanIn } from "../api/client";
import {
  ENTRY_PREFIX,
  EXIT_PREFIX,
  pickOwners,
  readOverrides,
  SETTINGS_PREFIX,
  SIGNALS_PREFIX,
  writeOverrides,
  type Overrides,
  type Values,
} from "./overrides";
import { moveLegacyExitSettings, sameList, type RuleDefaults, type TradeRulesForm } from "./rules";

export type DirectionChoice = Direction | "both";

export interface Universe {
  watchlist: string;
  tickers: string;
}

export interface ScanForm {
  universe: Universe;
  direction: DirectionChoice;
  families: Family[];
  period: string;
  benchmark: string;
  settings: Overrides;
  signalParams: Overrides;
}

export interface EdgeForm {
  universe: Universe;
  direction: DirectionChoice;
  families: Family[];
  horizons: string;
  minEvents: number;
  period: string;
  signalParams: Overrides;
}

/** What one backtest tests: shared by the Backtest and the Sweep page. */
export interface BacktestSetup extends TradeRulesForm {
  ticker: string;
  signal: string;
  period: string;
  settings: Overrides;
  /** Parameters of the selected signal. */
  signalParams: Values;
}

export interface BacktestForm extends BacktestSetup {
  engines: string[];
}

type SignalParamsIn = NonNullable<ScanIn["signal_params"]>;

const FAMILIES: readonly Family[] = ["trend", "momentum", "breakout", "mean_reversion", "volume", "pattern"];

const list = (value: string | null): string[] =>
  (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const number = (value: string | null): number | null => {
  if (value === null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const direction = (value: string | null): DirectionChoice =>
  value === "long" || value === "short" ? value : "both";

const families = (value: string | null): Family[] =>
  list(value).filter((item): item is Family => (FAMILIES as readonly string[]).includes(item));

export const tickerList = (text: string): string[] =>
  list(text.replace(/[\s;]+/g, ",")).map((ticker) => ticker.toUpperCase());

function readUniverse(params: URLSearchParams): Universe {
  return { watchlist: params.get("w") ?? "", tickers: params.get("t") ?? "" };
}

function writeUniverse(params: URLSearchParams, universe: Universe): void {
  if (universe.watchlist) params.set("w", universe.watchlist);
  else if (universe.tickers.trim()) params.set("t", tickerList(universe.tickers).join(","));
}

function universeBody(universe: Universe): { watchlist?: string; tickers?: string[] } | null {
  if (universe.watchlist) return { watchlist: universe.watchlist };
  const tickers = tickerList(universe.tickers);
  return tickers.length ? { tickers } : null;
}

function setIf(params: URLSearchParams, key: string, value: string | number | null | undefined): void {
  if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
}

// --- Scan -----------------------------------------------------------------

export function readScanForm(params: URLSearchParams): ScanForm {
  return {
    universe: readUniverse(params),
    direction: direction(params.get("dir")),
    families: families(params.get("fam")),
    period: params.get("p") ?? "",
    benchmark: (params.get("b") ?? "").toUpperCase(),
    settings: readOverrides(params, SETTINGS_PREFIX),
    signalParams: readOverrides(params, SIGNALS_PREFIX),
  };
}

export function writeScanForm(form: ScanForm): URLSearchParams {
  const params = new URLSearchParams();
  writeUniverse(params, form.universe);
  if (form.direction !== "both") params.set("dir", form.direction);
  if (form.families.length) params.set("fam", form.families.join(","));
  setIf(params, "p", form.period);
  setIf(params, "b", form.benchmark.trim().toUpperCase());
  writeOverrides(params, SETTINGS_PREFIX, form.settings);
  writeOverrides(params, SIGNALS_PREFIX, form.signalParams);
  return params;
}

/** The scan request without the account, which the page adds from browser storage. */
export function scanBody(form: ScanForm): ScanIn | null {
  const universe = universeBody(form.universe);
  if (!universe) return null;
  return {
    ...universe,
    families: form.families,
    direction: form.direction === "both" ? null : form.direction,
    period: form.period || null,
    benchmark: form.benchmark.trim().toUpperCase() || null,
    settings: form.settings,
    signal_params: form.signalParams as SignalParamsIn,
  };
}

// --- Edge -----------------------------------------------------------------

export function readEdgeForm(params: URLSearchParams): EdgeForm {
  return {
    universe: readUniverse(params),
    direction: direction(params.get("dir")),
    families: families(params.get("fam")),
    horizons: params.get("h") ?? "5,10,20",
    minEvents: number(params.get("n")) ?? 20,
    period: params.get("p") ?? "",
    signalParams: readOverrides(params, SIGNALS_PREFIX),
  };
}

export function writeEdgeForm(form: EdgeForm): URLSearchParams {
  const params = new URLSearchParams();
  writeUniverse(params, form.universe);
  if (form.direction !== "both") params.set("dir", form.direction);
  if (form.families.length) params.set("fam", form.families.join(","));
  setIf(params, "h", list(form.horizons).join(","));
  setIf(params, "n", form.minEvents);
  setIf(params, "p", form.period);
  writeOverrides(params, SIGNALS_PREFIX, form.signalParams);
  return params;
}

export function parseHorizons(text: string): number[] {
  return list(text)
    .map(Number)
    .filter((value) => Number.isInteger(value) && value > 0);
}

export function edgeBody(form: EdgeForm): EdgeIn | null {
  const universe = universeBody(form.universe);
  const horizons = parseHorizons(form.horizons);
  if (!universe || !horizons.length) return null;
  return {
    ...universe,
    families: form.families,
    direction: form.direction === "both" ? null : form.direction,
    horizons,
    min_events: form.minEvents,
    period: form.period || null,
    signal_params: form.signalParams as SignalParamsIn,
  };
}

// --- Backtest ---------------------------------------------------------------

/** Rules the URL leaves out are the server's defaults. */
export function readBacktestForm(params: URLSearchParams, defaults: RuleDefaults): BacktestForm {
  const engines = list(params.get("eng"));
  return { ...readBacktestSetup(params, defaults), engines: engines.length ? engines : ["vectorized"] };
}

export function readBacktestSetup(params: URLSearchParams, defaults: RuleDefaults): BacktestSetup {
  const signal = params.get("signal") ?? "";
  const entry = params.get("entry") || defaults.default_entry;
  const exitList = params.get("exit");
  const exits = exitList === null ? [...defaults.default_exits] : list(exitList).filter((name) => name !== "none");
  const { settings, exitParams } = moveLegacyExitSettings(readOverrides(params, SETTINGS_PREFIX), readOverrides(params, EXIT_PREFIX));
  return {
    ticker: (params.get("ticker") ?? "").toUpperCase(),
    signal,
    period: params.get("p") ?? "",
    settings,
    signalParams: (signal && readOverrides(params, SIGNALS_PREFIX)[signal]) || {},
    entry,
    entryParams: readOverrides(params, ENTRY_PREFIX)[entry] ?? {},
    exits,
    exitParams: pickOwners(exitParams, exits),
  };
}

/** With `defaults`, rules equal to them are left out, so unchanged links stay short. */
export function writeBacktestForm(form: BacktestForm, defaults?: RuleDefaults): URLSearchParams {
  return writeBacktestSetup(form, defaults, form.engines);
}

/** `engines` belong to a backtest only: a sweep always runs on one engine. */
export function writeBacktestSetup(form: BacktestSetup, defaults?: RuleDefaults, engines: string[] = []): URLSearchParams {
  const params = new URLSearchParams();
  setIf(params, "ticker", form.ticker.trim().toUpperCase());
  setIf(params, "signal", form.signal);
  setIf(params, "eng", engines.join(","));
  setIf(params, "p", form.period);
  if (form.entry !== defaults?.default_entry) setIf(params, "entry", form.entry);
  if (!defaults || !sameList(form.exits, defaults.default_exits)) params.set("exit", form.exits.join(",") || "none");
  writeOverrides(params, SETTINGS_PREFIX, form.settings);
  if (form.signal) writeOverrides(params, SIGNALS_PREFIX, { [form.signal]: form.signalParams });
  writeOverrides(params, ENTRY_PREFIX, { [form.entry]: form.entryParams });
  writeOverrides(params, EXIT_PREFIX, pickOwners(form.exitParams, form.exits));
  return params;
}

/** The backtest request without the account, which the page adds from browser storage. */
export function backtestBody(form: BacktestForm): BacktestIn | null {
  const setup = setupBody(form);
  return setup && form.engines.length ? { ...setup, engines: form.engines } : null;
}

/** The setup part of a backtest or sweep request; null until a ticker and a signal are chosen. */
export function setupBody(form: BacktestSetup): BacktestSetupIn | null {
  if (!form.ticker.trim() || !form.signal) return null;
  return {
    ticker: form.ticker.trim().toUpperCase(),
    signal: form.signal,
    period: form.period || null,
    params: form.signalParams as SignalParamsIn[string],
    settings: form.settings,
    entry: { name: form.entry, params: form.entryParams as SignalParamsIn[string] },
    exits: form.exits.map((name) => ({ name, params: (form.exitParams[name] ?? {}) as SignalParamsIn[string] })),
  };
}
