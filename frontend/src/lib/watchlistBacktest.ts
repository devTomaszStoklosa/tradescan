/**
 * Watchlist backtest: one setup on every ticker of a watchlist. The form and its URL, the request, and
 * helpers for the result.
 *
 * The URL holds the universe (`w=<watchlist>` or `t=<tickers>`), the setup with the Backtest page's keys
 * apart from the ticker, and the metric the tickers are ranked by (`m`).
 */
import type {
  ConfigOut,
  MetricSpreadOut,
  Period,
  TickerRunOut,
  WatchlistBacktestIn,
  WatchlistBacktestOut,
} from "../api/client";
import { type MetricKey } from "./compare";
import type { CsvRow } from "./csv";
import { DASH, fmtNumber, fmtPct, fmtSigned } from "./format";
import {
  readBacktestRules,
  readUniverse,
  rulesBody,
  universeBody,
  writeBacktestForm,
  writeBacktestSetup,
  writeUniverse,
  type BacktestRules,
  type Universe,
} from "./params";
import type { RuleDefaults } from "./rules";

export const DEFAULT_WATCHLIST_METRIC: MetricKey = "expectancy_r";

export interface WatchlistForm extends BacktestRules {
  universe: Universe;
}

export const PERIODS: { key: Period; label: string }[] = [
  { key: "full", label: "Full history" },
  { key: "in_sample", label: "In-sample" },
  { key: "out_of_sample", label: "Out-of-sample" },
];

// --- Form, URL and request ----------------------------------------------------------------------

/** Rules the URL leaves out are the server's defaults. */
export function readWatchlistForm(params: URLSearchParams, defaults: RuleDefaults): WatchlistForm {
  return { universe: readUniverse(params), ...readBacktestRules(params, defaults) };
}

/** With `defaults`, rules equal to them are left out, so unchanged links stay short. */
export function writeWatchlistForm(form: WatchlistForm, defaults?: RuleDefaults): URLSearchParams {
  const params = new URLSearchParams();
  writeUniverse(params, form.universe);
  for (const [key, value] of writeBacktestSetup(form, defaults)) params.append(key, value);
  return params;
}

/** The request without the account, which the page adds from browser storage; null until a universe and a signal are chosen. */
export function watchlistBody(form: WatchlistForm): WatchlistBacktestIn | null {
  const universe = universeBody(form.universe);
  const rules = rulesBody(form);
  return universe && rules ? { ...universe, ...rules } : null;
}

/** The Backtest page link for one ticker of the result: the same setup with the benchmark the run compared. */
export function backtestLink(
  form: WatchlistForm,
  ticker: string,
  result: WatchlistBacktestOut,
  config: ConfigOut,
): string {
  const { universe: _universe, ...rules } = form;
  const benchmark = result.benchmark ?? rules.benchmark;
  return `/backtest?${writeBacktestForm({ ...rules, ticker, benchmark, engines: [result.engine] }, config).toString()}`;
}

// --- Results --------------------------------------------------------------------------------------

export const periodMetrics = (row: TickerRunOut, period: Period) => (period === "full" ? row.metrics : row[period]);

export function rowValue(row: TickerRunOut, period: Period, metric: MetricKey): number | null {
  const metrics = periodMetrics(row, period);
  if (!metrics) return null;
  if (metric === "profit_factor" && metrics.profit_factor_infinite) return Infinity;
  return metrics[metric];
}

export function spreadOf(result: WatchlistBacktestOut, period: Period, metric: MetricKey): MetricSpreadOut | undefined {
  return result.periods.find((item) => item.period === period)?.spread.find((item) => item.metric === metric);
}

type SpreadField = "median" | "p25" | "p75" | "minimum" | "maximum";

/** A spread value; the API sends an infinite one (a profit factor without losers) as null with tickers left in. */
export function spreadValue(spread: MetricSpreadOut | undefined, field: SpreadField): number | null {
  if (!spread || !spread.tickers) return null;
  return spread[field] ?? Infinity;
}

const PERCENT = new Set<MetricKey>([
  "total_return_pct",
  "cagr_pct",
  "max_drawdown_pct",
  "win_rate_pct",
  "exposure_pct",
  "buy_hold_pct",
]);
const SIGNED = new Set<MetricKey>(["total_return_pct", "cagr_pct", "buy_hold_pct"]);

/** One metric value in that metric's own format. */
export function formatMetric(metric: MetricKey, value: number | null): string {
  if (value === null || Number.isNaN(value)) return DASH;
  if (value === Infinity) return "∞";
  if (metric === "trades") return fmtNumber(value, Number.isInteger(value) ? 0 : 1);
  if (metric === "expectancy_r") return `${fmtSigned(value)} R`;
  if (PERCENT.has(metric)) return fmtPct(value, 1, SIGNED.has(metric));
  return fmtNumber(value);
}

/** Every ticker with every metric of every period, for a CSV file. */
export function rowsToCsv(result: WatchlistBacktestOut): CsvRow[] {
  const prefixes: [Period, string][] = [
    ["full", "full"],
    ["in_sample", "is"],
    ["out_of_sample", "oos"],
  ];
  return result.rows.map((row) => {
    const keys = Object.keys(row.metrics) as (keyof typeof row.metrics)[];
    return {
      ticker: row.ticker,
      start: row.start,
      end: row.end,
      oos_start: row.split?.out_of_sample_start ?? "",
      ...Object.fromEntries(
        prefixes.flatMap(([period, prefix]) =>
          keys.map((key) => [`${prefix}_${key}`, periodMetrics(row, period)?.[key] ?? null]),
        ),
      ),
    };
  });
}
