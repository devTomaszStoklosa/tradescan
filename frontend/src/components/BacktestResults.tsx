import type { ReactNode } from "react";

import type { BacktestOut, EngineRunOut, MetricsOut, TradeOut } from "../api/client";
import { bestIndexes, metricValue, type MetricKey } from "../lib/compare";
import { DASH, fmtNumber, fmtPct, fmtPrice, fmtSigned, fmtSize, tone } from "../lib/format";
import { DataTable, type Column } from "./DataTable";
import { StatTile } from "./ui";

interface Metric {
  key: MetricKey;
  label: string;
  format: (metrics: MetricsOut) => string;
  /** Higher is better (drawdown is negative, so the value closest to zero ranks first). Unranked metrics only describe the run. */
  ranked?: boolean;
}

export const METRICS: Metric[] = [
  { key: "total_return_pct", label: "Total return", format: (m) => fmtPct(m.total_return_pct, 2, true), ranked: true },
  { key: "cagr_pct", label: "CAGR", format: (m) => fmtPct(m.cagr_pct, 2, true), ranked: true },
  { key: "max_drawdown_pct", label: "Max drawdown", format: (m) => fmtPct(m.max_drawdown_pct, 2), ranked: true },
  { key: "sharpe", label: "Sharpe", format: (m) => fmtNumber(m.sharpe), ranked: true },
  { key: "sortino", label: "Sortino", format: (m) => fmtNumber(m.sortino), ranked: true },
  { key: "trades", label: "Trades", format: (m) => String(m.trades) },
  { key: "win_rate_pct", label: "Win rate", format: (m) => fmtPct(m.win_rate_pct), ranked: true },
  {
    key: "profit_factor",
    label: "Profit factor",
    format: (m) => (m.profit_factor_infinite ? "∞" : fmtNumber(m.profit_factor)),
    ranked: true,
  },
  { key: "expectancy_r", label: "Expectancy", format: (m) => `${fmtSigned(m.expectancy_r)} R`, ranked: true },
  { key: "sqn", label: "SQN", format: (m) => fmtNumber(m.sqn), ranked: true },
  { key: "exposure_pct", label: "Exposure", format: (m) => fmtPct(m.exposure_pct) },
  { key: "buy_hold_pct", label: "Buy & hold", format: (m) => fmtPct(m.buy_hold_pct, 2, true) },
];

export function KeyMetrics({ run }: { run: EngineRunOut }) {
  const m = run.metrics;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      <StatTile
        label="Total return"
        value={fmtPct(m.total_return_pct, 1, true)}
        valueClass={tone(m.total_return_pct)}
        sub={`buy & hold ${fmtPct(m.buy_hold_pct, 1, true)}`}
      />
      <StatTile label="Max drawdown" value={fmtPct(m.max_drawdown_pct, 1)} valueClass="text-down" sub={`CAGR ${fmtPct(m.cagr_pct, 1, true)}`} />
      <StatTile label="Win rate" value={fmtPct(m.win_rate_pct, 0)} sub={`${m.trades} trades`} />
      <StatTile
        label="Profit factor"
        value={m.profit_factor_infinite ? "∞" : fmtNumber(m.profit_factor)}
        valueClass={m.profit_factor !== null && m.profit_factor < 1 ? "text-down" : "text-up"}
      />
      <StatTile label="Expectancy" value={`${fmtSigned(m.expectancy_r)} R`} valueClass={tone(m.expectancy_r)} sub={`SQN ${fmtNumber(m.sqn)}`} />
      <StatTile label="Sharpe" value={fmtNumber(m.sharpe)} sub={`exposure ${fmtPct(m.exposure_pct, 0)}`} />
    </div>
  );
}

/** True when every metric of every engine matches the first engine. */
export function enginesAgree(runs: { metrics: MetricsOut }[]): boolean {
  const [first, ...rest] = runs;
  if (!first || !rest.length) return false;
  return rest.every((run) =>
    METRICS.every(({ key }) => {
      const a = first.metrics[key];
      const b = run.metrics[key];
      return a === b || (typeof a === "number" && typeof b === "number" && Math.abs(a - b) <= 1e-6 * Math.max(1, Math.abs(a)));
    }),
  );
}

export interface MetricsColumn {
  key: string;
  header: ReactNode;
  /** Null when the column has no metrics, e.g. a run pinned before out-of-sample results; shown as dashes. */
  metrics: MetricsOut | null;
}

/** One column per engine, run or period; with `highlightBest`, the best value of each ranked metric is marked. */
export function MetricsTable({ columns, caption, highlightBest = false }: { columns: MetricsColumn[]; caption: string; highlightBest?: boolean }) {
  // `relative` keeps the absolutely positioned screen-reader labels inside the scroll area on narrow screens.
  return (
    <div className="relative overflow-x-auto rounded-xl border border-line bg-panel">
      <table className="w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line text-xs text-muted">
            <th scope="col" className="sticky left-0 bg-panel px-3 py-2 text-left font-medium">
              Metric
            </th>
            {columns.map((column) => (
              <th key={column.key} scope="col" className="px-3 py-2 text-right font-medium">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {METRICS.map((metric) => {
            const values = columns.map((column) => (column.metrics ? metricValue(column.metrics, metric.key) : null));
            const best = highlightBest && metric.ranked ? bestIndexes(values) : null;
            return (
              <tr key={metric.key} className="border-b border-line last:border-0">
                <th scope="row" className="sticky left-0 bg-panel px-3 py-1.5 text-left font-normal whitespace-nowrap text-muted">
                  {metric.label}
                </th>
                {columns.map((column, index) => (
                  <td key={column.key} className={`num px-3 py-1.5 text-right whitespace-nowrap ${best?.has(index) ? "bg-up/10 font-semibold" : ""}`}>
                    {column.metrics ? metric.format(column.metrics) : DASH}
                    {best?.has(index) && <span className="sr-only"> (best)</span>}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function MetricsComparison({ result }: { result: BacktestOut }) {
  const agree = enginesAgree(result.runs);
  const columns = result.runs.map((run) => ({ key: run.engine, header: <span className="capitalize">{run.engine}</span>, metrics: run.metrics }));
  return (
    <div className="space-y-2">
      {result.runs.length > 1 && (
        <p className={`text-sm ${agree ? "text-up" : "text-warn"}`}>
          {agree ? "✓ Both engines produced identical results." : "Engines differ: compare the trades below."}
        </p>
      )}
      <MetricsTable columns={columns} caption="Backtest metrics by engine" />
    </div>
  );
}

const REASON_STYLE: Record<string, string> = {
  target: "text-up",
  stop: "text-down",
  time: "text-muted",
  open: "text-accent",
};

const tradeColumns: Column<TradeOut>[] = [
  { key: "signal", header: "Signal", sortValue: (t) => t.signal_date, render: (t) => t.signal_date },
  { key: "entry", header: "Entry", sortValue: (t) => t.entry_date, render: (t) => t.entry_date },
  { key: "exit", header: "Exit", sortValue: (t) => t.exit_date, render: (t) => t.exit_date },
  { key: "entryPrice", header: "Entry price", align: "right", render: (t) => fmtPrice(t.entry_price) },
  { key: "exitPrice", header: "Exit price", align: "right", render: (t) => fmtPrice(t.exit_price) },
  { key: "size", header: "Size", align: "right", sortValue: (t) => t.size, render: (t) => fmtSize(t.size) },
  {
    key: "pnl",
    header: "P&L",
    align: "right",
    sortValue: (t) => t.pnl,
    render: (t) => <span className={tone(t.pnl)}>{fmtSigned(t.pnl)}</span>,
  },
  {
    key: "r",
    header: "R",
    align: "right",
    sortValue: (t) => t.r_multiple,
    render: (t) => <span className={tone(t.r_multiple)}>{fmtSigned(t.r_multiple)}</span>,
  },
  {
    key: "reason",
    header: "Exit reason",
    sortValue: (t) => t.exit_reason,
    render: (t) => <span className={`text-xs font-medium uppercase ${REASON_STYLE[t.exit_reason] ?? ""}`}>{t.exit_reason}</span>,
  },
];

type TickerTrade = TradeOut & { ticker?: string };

const tickerColumn: Column<TickerTrade> = {
  key: "ticker",
  header: "Ticker",
  sortValue: (t) => t.ticker,
  render: (t) => <span className="font-mono font-semibold">{t.ticker}</span>,
};

/** Trades of one ticker, or of many with a ticker column (a portfolio's). */
export function TradesTable({ trades }: { trades: TickerTrade[] }) {
  const columns = trades.some((trade) => trade.ticker !== undefined) ? [tickerColumn, ...tradeColumns] : tradeColumns;
  return (
    <DataTable
      rows={trades}
      columns={columns}
      rowKey={(trade) => `${trade.ticker ?? ""}:${trade.entry_date}:${trade.exit_date}`}
      initialSort={{ key: "entry", direction: "desc" }}
      dense
      caption="Trades"
    />
  );
}
