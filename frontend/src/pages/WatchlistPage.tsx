import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import type { ConfigOut, Period, PeriodSummaryOut, SignalOut, TickerRunOut, WatchlistBacktestOut, WatchlistOut } from "../api/client";
import { useConfig, useSignals, useWatchlistBacktest, useWatchlists } from "../api/hooks";
import { METRICS } from "../components/BacktestResults";
import { BacktestSetupFields } from "../components/BacktestSetupFields";
import { DataTable, type Column } from "../components/DataTable";
import { PERIOD_NOTE } from "../components/OutOfSample";
import { UniversePicker } from "../components/UniverseFilters";
import { Button, DirectionBadge, EmptyState, ErrorBox, Field, Loading, Notice, PageHeader, Panel, Select, StatTile } from "../components/ui";
import { defaultWatchlist, LARGE_UNIVERSE, universeSize } from "../lib/choices";
import { MIN_TRADES, type MetricKey } from "../lib/compare";
import { downloadCsv } from "../lib/csv";
import { DASH, fmtNumber, fmtPct, fmtSigned, tone } from "../lib/format";
import { hasSetupProblems, resetSetup, setupChanges } from "../lib/setup";
import {
  backtestLink,
  DEFAULT_WATCHLIST_METRIC,
  formatMetric,
  PERIODS,
  readWatchlistForm,
  rowsToCsv,
  rowValue,
  spreadOf,
  spreadValue,
  watchlistBody,
  writeWatchlistForm,
  type WatchlistForm,
} from "../lib/watchlistBacktest";
import { useAccount, withAccount } from "../state/account";

const METRIC_KEYS = new Set<string>(METRICS.map((metric) => metric.key));
const readMetric = (value: string | null): MetricKey => (value && METRIC_KEYS.has(value) ? (value as MetricKey) : DEFAULT_WATCHLIST_METRIC);
const metricLabel = (metric: MetricKey) => METRICS.find((item) => item.key === metric)?.label ?? metric;

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

function WatchlistFormPanel({
  initial,
  config,
  signals,
  watchlists,
  busy,
  onSubmit,
}: {
  initial: WatchlistForm;
  config: ConfigOut;
  signals: SignalOut[];
  watchlists: WatchlistOut[];
  busy: boolean;
  onSubmit: (form: WatchlistForm) => void;
}) {
  const withUniverse = (form: WatchlistForm): WatchlistForm =>
    form.universe.watchlist || form.universe.tickers ? form : { ...form, universe: { watchlist: defaultWatchlist(watchlists), tickers: "" } };
  const [draft, setDraft] = useState(() => withUniverse(initial));
  useEffect(() => setDraft(withUniverse(initial)), [initial, watchlists]);
  const changes = setupChanges(draft, config);
  const invalid = !watchlistBody(draft) || hasSetupProblems(draft, config, signals);
  const watchlistBenchmark = watchlists.find((item) => item.name === draft.universe.watchlist)?.benchmark;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!invalid) onSubmit(draft);
  };

  return (
    <Panel>
      <form onSubmit={submit} noValidate className="space-y-4">
        <UniversePicker value={draft.universe} onChange={(universe) => setDraft({ ...draft, universe })} watchlists={watchlists} />
        <BacktestSetupFields
          draft={draft}
          onChange={setDraft}
          config={config}
          signals={signals}
          defaultBenchmark={watchlistBenchmark ?? config.benchmark}
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted">Every ticker runs on the vectorized engine, split in-sample and out-of-sample on its own history.</p>
          <div className="flex items-center gap-2">
            {changes > 0 && (
              <Button variant="ghost" onClick={() => setDraft(resetSetup(draft, config))}>
                Reset {changes} changed
              </Button>
            )}
            <Button type="submit" variant="primary" disabled={busy || invalid} className="h-9 px-5">
              {busy ? "Running…" : "Run on every ticker"}
            </Button>
          </div>
        </div>
      </form>
    </Panel>
  );
}

const PERIOD_LABELS = Object.fromEntries(PERIODS.map((period) => [period.key, period.label])) as Record<Period, string>;

function SpreadTable({ result, metric }: { result: WatchlistBacktestOut; metric: MetricKey }) {
  const columns = useMemo<Column<Period>[]>(() => {
    const value = (field: "minimum" | "p25" | "median" | "p75" | "maximum") => (period: Period) =>
      formatMetric(metric, spreadValue(spreadOf(result, period, metric), field));
    const right = { align: "right" as const };
    return [
      { key: "period", header: "Period", render: (period) => PERIOD_LABELS[period] },
      { key: "tickers", header: "Tickers", ...right, render: (period) => String(spreadOf(result, period, metric)?.tickers ?? 0) },
      { key: "min", header: "Worst", ...right, render: value("minimum") },
      { key: "p25", header: "25%", ...right, render: value("p25") },
      { key: "median", header: "Median", ...right, render: value("median") },
      { key: "p75", header: "75%", ...right, render: value("p75") },
      { key: "max", header: "Best", ...right, render: value("maximum") },
      {
        key: "above",
        header: "Above break-even",
        ...right,
        render: (period) => fmtPct(spreadOf(result, period, metric)?.above_break_even_pct, 0),
      },
    ];
  }, [result, metric]);
  return <DataTable rows={PERIODS.map((period) => period.key)} columns={columns} rowKey={(period) => period} caption={`Spread of ${metricLabel(metric)} across tickers`} dense />;
}

const POOLED_COLUMNS: Column<PeriodSummaryOut>[] = [
  { key: "period", header: "Period", render: (row) => PERIOD_LABELS[row.period] },
  { key: "tickers", header: "Tickers", align: "right", render: (row) => String(row.tickers) },
  { key: "trades", header: "Trades", align: "right", render: (row) => String(row.pooled.trades) },
  { key: "win", header: "Win rate", align: "right", render: (row) => fmtPct(row.pooled.win_rate_pct) },
  {
    key: "expectancy",
    header: "Expectancy",
    align: "right",
    render: (row) => <span className={tone(row.pooled.expectancy_r)}>{`${fmtSigned(row.pooled.expectancy_r)} R`}</span>,
  },
  {
    key: "pf",
    header: "Profit factor (R)",
    align: "right",
    render: (row) => (row.pooled.profit_factor_infinite ? "∞" : fmtNumber(row.pooled.profit_factor_r)),
  },
  { key: "sqn", header: "SQN", align: "right", render: (row) => fmtNumber(row.pooled.sqn) },
];

function TickerTable({ result, form, metric, config }: { result: WatchlistBacktestOut; form: WatchlistForm; metric: MetricKey; config: ConfigOut }) {
  const columns = useMemo<Column<TickerRunOut>[]>(() => {
    const label = metricLabel(metric);
    const valueColumn = (period: Period, header: string): Column<TickerRunOut> => ({
      key: period,
      header,
      title: `${label}, ${PERIOD_LABELS[period].toLowerCase()}`,
      align: "right",
      sortValue: (row) => rowValue(row, period, metric),
      render: (row) => formatMetric(metric, rowValue(row, period, metric)),
    });
    const fewTrades = (trades: number | undefined) => trades !== undefined && trades < MIN_TRADES;
    return [
      {
        key: "ticker",
        header: "Ticker",
        sortValue: (row) => row.ticker,
        render: (row) => (
          <Link to={backtestLink(form, row.ticker, result, config)} className="font-mono font-semibold text-accent hover:underline" title="Open in Backtest">
            {row.ticker}
          </Link>
        ),
      },
      {
        key: "trades",
        header: "Trades",
        align: "right",
        sortValue: (row) => row.metrics.trades,
        render: (row) => (
          <span className={fewTrades(row.metrics.trades) ? "text-warn" : ""} title={fewTrades(row.metrics.trades) ? "Too few trades to trust" : undefined}>
            {row.metrics.trades}
          </span>
        ),
      },
      valueColumn("full", `${label}`),
      valueColumn("in_sample", "In-sample"),
      valueColumn("out_of_sample", "Out-of-sample"),
      {
        key: "oos_trades",
        header: "OOS trades",
        title: "Trades out-of-sample",
        align: "right",
        sortValue: (row) => row.out_of_sample?.trades,
        render: (row) => (row.out_of_sample ? String(row.out_of_sample.trades) : DASH),
      },
      {
        key: "return",
        header: "Total return",
        align: "right",
        sortValue: (row) => row.metrics.total_return_pct,
        render: (row) => <span className={tone(row.metrics.total_return_pct)}>{fmtPct(row.metrics.total_return_pct, 1, true)}</span>,
      },
      {
        key: "drawdown",
        header: "Max drawdown",
        align: "right",
        sortValue: (row) => row.metrics.max_drawdown_pct,
        render: (row) => fmtPct(row.metrics.max_drawdown_pct, 1),
      },
      {
        key: "buy_hold",
        header: "Buy & hold",
        align: "right",
        sortValue: (row) => row.metrics.buy_hold_pct,
        render: (row) => fmtPct(row.metrics.buy_hold_pct, 1, true),
      },
    ];
  }, [result, form, metric, config]);
  return (
    <DataTable
      rows={result.rows}
      columns={columns}
      rowKey={(row) => row.ticker}
      initialSort={{ key: "full", direction: "desc" }}
      caption={`Every ticker's ${metricLabel(metric)}`}
      dense
    />
  );
}

function WatchlistView({
  result,
  form,
  metric,
  onMetric,
  config,
}: {
  result: WatchlistBacktestOut;
  form: WatchlistForm;
  metric: MetricKey;
  onMetric: (metric: MetricKey) => void;
  config: ConfigOut;
}) {
  const label = metricLabel(metric);
  const used = result.config;
  const periods = Object.fromEntries(result.periods.map((period) => [period.period, period])) as Record<Period, PeriodSummaryOut>;
  const median = (period: Period) => formatMetric(metric, spreadValue(spreadOf(result, period, metric), "median"));
  const oosSpread = spreadOf(result, "out_of_sample", metric);
  const few = result.rows.filter((row) => row.metrics.trades < MIN_TRADES).length;
  const exits = result.exits.map((exit) => exit.description).join("; ") || "none, only the stop";
  const filters = result.filters.map((filter) => filter.description).join("; ");

  return (
    <div className="space-y-4">
      <div className="space-y-1 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-lg font-semibold">{result.universe}</span>
          <span className="font-medium">{result.signal}</span>
          <DirectionBadge direction={result.direction} />
          <span className="text-muted">{result.description}</span>
        </div>
        <p className="text-muted">
          {plural(result.rows.length, "ticker")} on the {result.engine} engine · each split at its own last {used.oos_pct}% · risk{" "}
          {fmtNumber(used.risk_pct, 2)}% · costs {fmtNumber(used.commission_pct, 2)}% + {fmtNumber(used.slippage_pct, 2)}%
        </p>
        {filters && (
          <p className="text-muted">
            Filters: {filters}
            {result.benchmark && ` · benchmark ${result.benchmark}`}
          </p>
        )}
        <p className="text-muted">
          Entry: {result.entry.description} · initial stop {fmtNumber(used.atr_mult, 2)} × ATR({used.atr_period}) · exits: {exits}
        </p>
      </div>
      {result.missing.length > 0 && <Notice>No data for: {result.missing.join(", ")}</Notice>}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Rank by">
          <Select value={metric} onChange={(event) => onMetric(event.target.value as MetricKey)}>
            {METRICS.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <StatTile label={`Median ${label}`} value={`${median("in_sample")} → ${median("out_of_sample")}`} sub="in-sample → out-of-sample, across tickers" />
        <StatTile
          label="Tickers above break-even out-of-sample"
          value={oosSpread?.above_break_even_pct == null ? DASH : fmtPct(oosSpread.above_break_even_pct, 0)}
          sub={oosSpread?.above_break_even_pct == null ? `${label} has no break-even` : `of ${plural(oosSpread.tickers, "ticker")} with a value`}
        />
        <StatTile
          label="Pooled expectancy"
          value={`${fmtSigned(periods.in_sample?.pooled.expectancy_r)} → ${fmtSigned(periods.out_of_sample?.pooled.expectancy_r)} R`}
          sub={`in-sample → out-of-sample, ${periods.full?.pooled.trades ?? 0} trades in all`}
        />
        <StatTile
          label="Tickers with few trades"
          value={`${few} of ${result.rows.length}`}
          valueClass={few ? "text-warn" : undefined}
          sub={`fewer than ${MIN_TRADES} trades over the full history`}
        />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <section className="min-w-0 space-y-2">
          <h2 className="text-sm font-semibold">Spread of {label} across tickers</h2>
          <SpreadTable result={result} metric={metric} />
          <p className="text-xs text-muted">Tickers without a value (no trades) are left out. A setting that only one ticker carries is likely luck.</p>
        </section>
        <section className="min-w-0 space-y-2">
          <h2 className="text-sm font-semibold">All tickers' trades pooled, in R</h2>
          <DataTable rows={result.periods} columns={POOLED_COLUMNS} rowKey={(row) => row.period} caption="All tickers' trades pooled, by period" dense />
          <p className="text-xs text-muted">Pooled in R, since each ticker's equity compounds on its own.</p>
        </section>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{plural(result.rows.length, "ticker")}</h2>
        <Button onClick={() => downloadCsv(`tradescan-watchlist-${result.universe}-${result.signal}.csv`, rowsToCsv(result))}>Export CSV</Button>
      </div>
      <TickerTable result={result} form={form} metric={metric} config={config} />
      <p className="text-xs text-muted">
        {PERIOD_NOTE} Click a ticker to open its backtest. Today's index members carry survivorship bias.
      </p>
    </div>
  );
}

export function WatchlistPage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const signals = useSignals();
  const watchlists = useWatchlists();
  const { account } = useAccount();
  const form = useMemo(() => (config.data ? readWatchlistForm(params, config.data) : null), [params, config.data]);
  const metric = readMetric(params.get("m"));
  const body = useMemo(() => {
    const request = form && watchlistBody(form);
    return form && request ? { ...request, settings: withAccount(form.settings, account) } : null;
  }, [form, account]);
  const run = useWatchlistBacktest(body);

  const failed = config.error ?? signals.error ?? watchlists.error;
  if (failed) return <ErrorBox error={failed} />;
  if (!config.data || !signals.data || !watchlists.data || !form) return <Loading message="Connecting to the tradescan server…" />;
  const defaults = config.data;

  const withMetric = (next: URLSearchParams, value: MetricKey) => {
    if (value !== DEFAULT_WATCHLIST_METRIC) next.set("m", value);
    return next;
  };

  return (
    <>
      <PageHeader
        title="Watchlist"
        subtitle="One setup on every ticker of a watchlist. A setting that only works on one ticker shows in the spread and the out-of-sample columns."
      />
      <WatchlistFormPanel
        initial={form}
        config={defaults}
        signals={signals.data}
        watchlists={watchlists.data}
        busy={run.isFetching}
        onSubmit={(next) => setParams(withMetric(writeWatchlistForm(next, defaults), metric))}
      />
      {!body && <EmptyState title="Choose a watchlist and a signal">Every ticker is backtested on its own and the results are compared.</EmptyState>}
      {run.isLoading && (
        <Loading
          message={
            universeSize(form.universe, watchlists.data) > LARGE_UNIVERSE
              ? "Backtesting every ticker of a large universe… The first run downloads every ticker and takes 1–2 minutes; cached runs take under a minute."
              : "Downloading history and backtesting every ticker…"
          }
        />
      )}
      {run.isError && <ErrorBox error={run.error} onRetry={() => run.refetch()} />}
      {run.data && (
        <WatchlistView
          result={run.data}
          form={form}
          metric={metric}
          onMetric={(value) => setParams(withMetric(writeWatchlistForm(form, defaults), value), { replace: true })}
          config={defaults}
        />
      )}
    </>
  );
}
