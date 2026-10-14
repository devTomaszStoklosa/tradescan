/**
 * Form state <-> URL search params. Keeping requests in the URL makes results shareable,
 * survives reloads, and lets the query cache show earlier results on back navigation.
 * Parameter overrides travel as `set.<section>.<name>` and `sig.<signal>.<name>` (see overrides.ts).
 */
import type { BacktestIn, Direction, EdgeIn, Family, ScanIn } from "../api/client";
import { readOverrides, SETTINGS_PREFIX, SIGNALS_PREFIX, writeOverrides, type Overrides, type Values } from "./overrides";

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

export interface BacktestForm {
  ticker: string;
  signal: string;
  engines: string[];
  period: string;
  settings: Overrides;
  /** Parameters of the selected signal. */
  signalParams: Values;
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

export function readBacktestForm(params: URLSearchParams): BacktestForm {
  const engines = list(params.get("eng"));
  const signal = params.get("signal") ?? "";
  return {
    ticker: (params.get("ticker") ?? "").toUpperCase(),
    signal,
    engines: engines.length ? engines : ["vectorized"],
    period: params.get("p") ?? "",
    settings: readOverrides(params, SETTINGS_PREFIX),
    signalParams: (signal && readOverrides(params, SIGNALS_PREFIX)[signal]) || {},
  };
}

export function writeBacktestForm(form: BacktestForm): URLSearchParams {
  const params = new URLSearchParams();
  setIf(params, "ticker", form.ticker.trim().toUpperCase());
  setIf(params, "signal", form.signal);
  setIf(params, "eng", form.engines.join(","));
  setIf(params, "p", form.period);
  writeOverrides(params, SETTINGS_PREFIX, form.settings);
  if (form.signal) writeOverrides(params, SIGNALS_PREFIX, { [form.signal]: form.signalParams });
  return params;
}

/** The backtest request without the account, which the page adds from browser storage. */
export function backtestBody(form: BacktestForm): BacktestIn | null {
  if (!form.ticker.trim() || !form.signal || !form.engines.length) return null;
  return {
    ticker: form.ticker.trim().toUpperCase(),
    signal: form.signal,
    engines: form.engines,
    period: form.period || null,
    params: form.signalParams as SignalParamsIn[string],
    settings: form.settings,
  };
}
