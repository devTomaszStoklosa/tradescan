/**
 * Form state <-> URL search params. Keeping requests in the URL makes results shareable,
 * survives reloads, and lets the query cache show earlier results on back navigation.
 */
import type { BacktestIn, Direction, EdgeIn, Family, ScanIn } from "../api/client";

export type DirectionChoice = Direction | "both";

export interface Universe {
  watchlist: string;
  tickers: string;
}

export interface ScanForm {
  universe: Universe;
  direction: DirectionChoice;
  families: Family[];
  freshBars: number | null;
  minScore: number | null;
}

export interface EdgeForm {
  universe: Universe;
  direction: DirectionChoice;
  families: Family[];
  horizons: string;
  minEvents: number;
  period: string;
}

export interface BacktestForm {
  ticker: string;
  signal: string;
  engines: string[];
  period: string;
  atrMult: number | null;
  targetR: number | null;
  maxHold: number | null;
  commissionPct: number | null;
  slippagePct: number | null;
}

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
    freshBars: number(params.get("fresh")),
    minScore: number(params.get("min")),
  };
}

export function writeScanForm(form: ScanForm): URLSearchParams {
  const params = new URLSearchParams();
  writeUniverse(params, form.universe);
  if (form.direction !== "both") params.set("dir", form.direction);
  if (form.families.length) params.set("fam", form.families.join(","));
  setIf(params, "fresh", form.freshBars);
  setIf(params, "min", form.minScore);
  return params;
}

export function scanBody(form: ScanForm): ScanIn | null {
  const universe = universeBody(form.universe);
  if (!universe) return null;
  return {
    ...universe,
    families: form.families,
    direction: form.direction === "both" ? null : form.direction,
    fresh_bars: form.freshBars,
    min_score: form.minScore,
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
  };
}

// --- Backtest ---------------------------------------------------------------

export function readBacktestForm(params: URLSearchParams): BacktestForm {
  const engines = list(params.get("eng"));
  return {
    ticker: (params.get("ticker") ?? "").toUpperCase(),
    signal: params.get("signal") ?? "",
    engines: engines.length ? engines : ["vectorized"],
    period: params.get("p") ?? "",
    atrMult: number(params.get("atr")),
    targetR: number(params.get("tr")),
    maxHold: number(params.get("hold")),
    commissionPct: number(params.get("comm")),
    slippagePct: number(params.get("slip")),
  };
}

export function writeBacktestForm(form: BacktestForm): URLSearchParams {
  const params = new URLSearchParams();
  setIf(params, "ticker", form.ticker.trim().toUpperCase());
  setIf(params, "signal", form.signal);
  setIf(params, "eng", form.engines.join(","));
  setIf(params, "p", form.period);
  setIf(params, "atr", form.atrMult);
  setIf(params, "tr", form.targetR);
  setIf(params, "hold", form.maxHold);
  setIf(params, "comm", form.commissionPct);
  setIf(params, "slip", form.slippagePct);
  return params;
}

export function backtestBody(form: BacktestForm): BacktestIn | null {
  if (!form.ticker.trim() || !form.signal || !form.engines.length) return null;
  return {
    ticker: form.ticker.trim().toUpperCase(),
    signal: form.signal,
    engines: form.engines,
    period: form.period || null,
    atr_mult: form.atrMult,
    target_r: form.targetR,
    max_hold_bars: form.maxHold,
    commission_pct: form.commissionPct,
    slippage_pct: form.slippagePct,
  };
}
