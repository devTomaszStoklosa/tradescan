import type { BacktestOut, EngineRunOut, MetricsOut, TradeOut } from "../api/client";
import { fmtNumber, fmtPct, fmtPrice, fmtSigned, fmtSize, tone } from "../lib/format";
import { DataTable, type Column } from "./DataTable";
import { StatTile } from "./ui";

type MetricKey = Exclude<keyof MetricsOut, "profit_factor_infinite">;

const METRICS: { key: MetricKey; label: string; format: (metrics: MetricsOut) => string }[] = [
  { key: "total_return_pct", label: "Total return", format: (m) => fmtPct(m.total_return_pct, 2, true) },
  { key: "cagr_pct", label: "CAGR", format: (m) => fmtPct(m.cagr_pct, 2, true) },
  { key: "max_drawdown_pct", label: "Max drawdown", format: (m) => fmtPct(m.max_drawdown_pct, 2) },
  { key: "sharpe", label: "Sharpe", format: (m) => fmtNumber(m.sharpe) },
  { key: "sortino", label: "Sortino", format: (m) => fmtNumber(m.sortino) },
  { key: "trades", label: "Trades", format: (m) => String(m.trades) },
  { key: "win_rate_pct", label: "Win rate", format: (m) => fmtPct(m.win_rate_pct) },
  { key: "profit_factor", label: "Profit factor", format: (m) => (m.profit_factor_infinite ? "∞" : fmtNumber(m.profit_factor)) },
  { key: "expectancy_r", label: "Expectancy", format: (m) => `${fmtSigned(m.expectancy_r)} R` },
  { key: "sqn", label: "SQN", format: (m) => fmtNumber(m.sqn) },
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
export function enginesAgree(runs: EngineRunOut[]): boolean {
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

export function MetricsComparison({ result }: { result: BacktestOut }) {
  const agree = enginesAgree(result.runs);
  return (
    <div className="space-y-2">
      {result.runs.length > 1 && (
        <p className={`text-sm ${agree ? "text-up" : "text-warn"}`}>
          {agree ? "✓ Both engines produced identical results." : "Engines differ: compare the trades below."}
        </p>
      )}
      <div className="overflow-x-auto rounded-xl border border-line bg-panel">
        <table className="w-full text-sm">
          <caption className="sr-only">Backtest metrics by engine</caption>
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th scope="col" className="px-3 py-2 text-left font-medium">
                Metric
              </th>
              {result.runs.map((run) => (
                <th key={run.engine} scope="col" className="px-3 py-2 text-right font-medium capitalize">
                  {run.engine}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {METRICS.map((metric) => (
              <tr key={metric.key} className="border-b border-line last:border-0">
                <th scope="row" className="px-3 py-1.5 text-left font-normal text-muted">
                  {metric.label}
                </th>
                {result.runs.map((run) => (
                  <td key={run.engine} className="num px-3 py-1.5 text-right">
                    {metric.format(run.metrics)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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

export function TradesTable({ trades }: { trades: TradeOut[] }) {
  return (
    <DataTable
      rows={trades}
      columns={tradeColumns}
      rowKey={(trade) => `${trade.entry_date}:${trade.exit_date}`}
      initialSort={{ key: "entry", direction: "desc" }}
      dense
      caption="Trades"
    />
  );
}
