import type { components } from "./schema";

type Schemas = components["schemas"];

export type AppliedRuleOut = Schemas["AppliedRuleOut"];
export type BacktestConfigOut = Schemas["BacktestConfigOut"];
export type BacktestIn = Schemas["BacktestIn"];
export type BacktestOut = Schemas["BacktestOut"];
/** What a backtest and a sweep share. */
export type BacktestSetupIn = Omit<BacktestIn, "engines">;
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
export type FilterRuleOut = Schemas["FilterRuleOut"];
export type HitOut = Schemas["HitOut"];
export type JournalOut = Schemas["JournalOut"];
export type JournalSummaryOut = Schemas["JournalSummaryOut"];
export type JournalTradeIn = Schemas["JournalTradeIn"];
export type JournalTradeOut = Schemas["JournalTradeOut"];
export type MetricsOut = Schemas["MetricsOut"];
export type MetricSpreadOut = Schemas["MetricSpreadOut"];
export type MonteCarloMethodOut = Schemas["MonteCarloMethodOut"];
export type MonteCarloOut = Schemas["MonteCarloOut"];
export type MonteCarloPathOut = Schemas["MonteCarloPathOut"];
export type ParamKind = Schemas["ParamKind"];
export type ParamSpecOut = Schemas["ParamSpecOut"];
export type PercentilesOut = Schemas["PercentilesOut"];
export type Period = Schemas["Period"];
export type PickOut = Schemas["PickOut"];
export type PinnedRunIn = Schemas["PinnedRunIn"];
export type PinnedRunOut = Schemas["PinnedRunOut"];
export type PinnedRunPatchIn = Schemas["PinnedRunPatchIn"];
export type PeriodSummaryOut = Schemas["PeriodSummaryOut"];
export type Point = Schemas["Point"];
export type PooledTradesOut = Schemas["PooledTradesOut"];
export type PortfolioIn = Schemas["PortfolioIn"];
export type PortfolioOut = Schemas["PortfolioOut"];
export type PortfolioPeriodOut = Schemas["PortfolioPeriodOut"];
export type PortfolioRunOut = Schemas["PortfolioRunOut"];
export type PortfolioStatsOut = Schemas["PortfolioStatsOut"];
export type PortfolioTradeOut = Schemas["PortfolioTradeOut"];
export type PriorityRuleOut = Schemas["PriorityRuleOut"];
export type Rebalance = Schemas["Rebalance"];
export type RegimeOut = Schemas["RegimeOut"];
export type RotationIn = Schemas["RotationIn"];
export type RotationOut = Schemas["RotationOut"];
export type RotationPeriodOut = Schemas["RotationPeriodOut"];
export type RotationRunOut = Schemas["RotationRunOut"];
export type RotationStatsOut = Schemas["RotationStatsOut"];
export type RuleIn = Schemas["RuleIn"];
export type RuleOut = Schemas["RuleOut"];
export type ScanIn = Schemas["ScanIn"];
export type ScanInputsOut = Schemas["ScanInputsOut"];
export type ScanOut = Schemas["ScanOut"];
export type SettingsSectionOut = Schemas["SettingsSectionOut"];
export type SignalOut = Schemas["SignalOut"];
export type SplitOut = Schemas["SplitOut"];
export type SuggestingRun = Schemas["SuggestingRun"];
export type SweepAxisIn = Schemas["SweepAxisIn"];
export type SweepAxisOut = Schemas["SweepAxisOut"];
export type SweepCellOut = Schemas["SweepCellOut"];
export type SweepIn = Schemas["SweepIn"];
export type SweepLimitsOut = Schemas["SweepLimitsOut"];
export type SweepOut = Schemas["SweepOut"];
export type SweepTarget = Schemas["SweepTarget"];
export type TargetsOut = Schemas["TargetsOut"];
export type TickerContributionOut = Schemas["TickerContributionOut"];
export type TickerRunOut = Schemas["TickerRunOut"];
export type TradeOut = Schemas["TradeOut"];
export type WalkForwardIn = Schemas["WalkForwardIn"];
export type WalkForwardOut = Schemas["WalkForwardOut"];
export type WalkForwardWindowOut = Schemas["WalkForwardWindowOut"];
export type WatchlistBacktestIn = Schemas["WatchlistBacktestIn"];
export type WatchlistBacktestOut = Schemas["WatchlistBacktestOut"];
export type WatchlistOut = Schemas["WatchlistOut"];
export type WindowPickOut = Schemas["WindowPickOut"];
export type WindowScheme = Schemas["WindowScheme"];

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

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

async function request<T>(path: string, init?: Pick<RequestInit, "method" | "body">): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json" },
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
  // 204 No Content: a removal has nothing to return.
  return (response.status === 204 ? undefined : await response.json()) as T;
}

const send = <T>(method: string, path: string, body?: unknown) =>
  request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

const post = <T>(path: string, body: unknown) => send<T>("POST", path, body);

export const api = {
  config: () => request<ConfigOut>("/config"),
  signals: () => request<SignalOut[]>("/signals"),
  watchlists: () => request<WatchlistOut[]>("/watchlists"),
  scan: (body: ScanIn) => post<ScanOut>("/scan", body),
  edge: (body: EdgeIn) => post<EdgeOut>("/edge", body),
  backtest: (body: BacktestIn) => post<BacktestOut>("/backtest", body),
  sweep: (body: SweepIn) => post<SweepOut>("/sweep", body),
  walkForward: (body: WalkForwardIn) => post<WalkForwardOut>("/walk-forward", body),
  watchlistBacktest: (body: WatchlistBacktestIn) => post<WatchlistBacktestOut>("/watchlist-backtest", body),
  portfolioBacktest: (body: PortfolioIn) => post<PortfolioOut>("/portfolio-backtest", body),
  rotationBacktest: (body: RotationIn) => post<RotationOut>("/rotation-backtest", body),
  chart: (body: ChartIn) => post<ChartOut>("/chart", body),
  runs: () => request<PinnedRunOut[]>("/runs"),
  pinRun: (body: PinnedRunIn) => post<PinnedRunOut>("/runs", body),
  updateRun: (id: string, body: PinnedRunPatchIn) =>
    send<PinnedRunOut>("PATCH", `/runs/${encodeURIComponent(id)}`, body),
  unpinRun: (id: string) => send<undefined>("DELETE", `/runs/${encodeURIComponent(id)}`),
  clearRuns: () => send<undefined>("DELETE", "/runs"),
  journal: () => request<JournalOut>("/journal"),
  logTrade: (body: JournalTradeIn) => post<JournalTradeOut>("/journal/trades", body),
  replaceTrade: (id: number, body: JournalTradeIn) => send<JournalTradeOut>("PUT", `/journal/trades/${id}`, body),
  deleteTrade: (id: number) => send<undefined>("DELETE", `/journal/trades/${id}`),
};

export type Api = typeof api;
