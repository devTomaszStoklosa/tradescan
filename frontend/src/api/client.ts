import type { components } from "./schema";

type Schemas = components["schemas"];

export type BacktestIn = Schemas["BacktestIn"];
export type BacktestOut = Schemas["BacktestOut"];
export type Candle = Schemas["Candle"];
export type ChartIn = Schemas["ChartIn"];
export type ChartOut = Schemas["ChartOut"];
export type ConfigOut = Schemas["ConfigOut"];
export type Direction = Schemas["Direction"];
export type EdgeIn = Schemas["EdgeIn"];
export type EdgeOut = Schemas["EdgeOut"];
export type EdgeRowOut = Schemas["EdgeRowOut"];
export type EdgeStatsOut = Schemas["EdgeStatsOut"];
export type EngineRunOut = Schemas["EngineRunOut"];
export type Family = Schemas["Family"];
export type HitOut = Schemas["HitOut"];
export type MetricsOut = Schemas["MetricsOut"];
export type ParamKind = Schemas["ParamKind"];
export type ParamSpecOut = Schemas["ParamSpecOut"];
export type Point = Schemas["Point"];
export type RegimeOut = Schemas["RegimeOut"];
export type ScanIn = Schemas["ScanIn"];
export type ScanOut = Schemas["ScanOut"];
export type SettingsSectionOut = Schemas["SettingsSectionOut"];
export type SignalOut = Schemas["SignalOut"];
export type TradeOut = Schemas["TradeOut"];
export type WatchlistOut = Schemas["WatchlistOut"];

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type ValidationIssue = { loc?: (string | number)[]; msg?: string };

function describe(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((issue) => {
        const field = (issue.loc ?? []).filter((part) => part !== "body").join(".");
        return field ? `${field}: ${issue.msg}` : (issue.msg ?? "invalid value");
      })
      .join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the tradescan server. Is `tradescan serve` running?");
  }
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      message = describe(((await response.json()) as { detail?: unknown }).detail, message);
    } catch {
      // Body was not JSON: keep the status text.
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  config: () => request<ConfigOut>("/config"),
  signals: () => request<SignalOut[]>("/signals"),
  watchlists: () => request<WatchlistOut[]>("/watchlists"),
  scan: (body: ScanIn) => post<ScanOut>("/scan", body),
  edge: (body: EdgeIn) => post<EdgeOut>("/edge", body),
  backtest: (body: BacktestIn) => post<BacktestOut>("/backtest", body),
  chart: (body: ChartIn) => post<ChartOut>("/chart", body),
};

export type Api = typeof api;
