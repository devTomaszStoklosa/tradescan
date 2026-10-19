import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import type {
  ConfigOut,
  MetricsOut,
  SignalOut,
  WalkForwardOut,
  WalkForwardWindowOut,
  WindowScheme,
} from "../api/client";
import { useConfig, useSignals, useWalkForward } from "../api/hooks";
import { METRICS, MetricsTable, TradesTable } from "../components/BacktestResults";
import { BacktestSetupFields } from "../components/BacktestSetupFields";
import { EquityChart, type EquityEvent, type EquitySeries } from "../components/charts/EquityChart";
import { DataTable, type Column } from "../components/DataTable";
import { SectionFields } from "../components/ParamFields";
import { SweptParameters } from "../components/SweepAxisFields";
import { describeCombination } from "../components/SweepHeatmap";
import { GroupHeading } from "../components/TradeRuleFields";
import {
  Button,
  DirectionBadge,
  EmptyState,
  ErrorBox,
  Field,
  Loading,
  Notice,
  PageHeader,
  Panel,
  Segmented,
  Select,
  StatTile,
} from "../components/ui";
import { WALK_FORWARD_PAGE_SECTIONS, WALK_FORWARD_SECTION } from "../lib/choices";
import { MIN_TRADES } from "../lib/compare";
import { downloadCsv, tradeRow } from "../lib/csv";
import { DASH, fmtNumber, fmtPct, tone } from "../lib/format";
import { hasSetupProblems } from "../lib/setup";
import type { SweepParam } from "../lib/sweep";
import {
  backtestLink,
  readWalkForwardForm,
  resetWalkForward,
  walkForwardBody,
  walkForwardChanges,
  walkForwardParams,
  walkForwardRuns,
  writeWalkForwardForm,
  type WalkForwardForm,
} from "../lib/walkForward";
import { useAccount, withAccount } from "../state/account";

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

const SCHEMES: { value: WindowScheme; label: string }[] = [
  { value: "rolling", label: "Rolling" },
  { value: "anchored", label: "Anchored" },
];

const metricLabel = (key: string) => METRICS.find((metric) => metric.key === key)?.label ?? key;

/** One metric of a run as the tables show it, e.g. "+1.20 R"; a dash without metrics. */
function metricText(metrics: MetricsOut | null | undefined, key: string): string {
  const metric = METRICS.find((item) => item.key === key);
  return metrics && metric ? metric.format(metrics) : DASH;
}

function WalkForwardFormPanel({
  initial,
  config,
  signals,
  busy,
  onSubmit,
}: {
  initial: WalkForwardForm;
  config: ConfigOut;
  signals: SignalOut[];
  busy: boolean;
  onSubmit: (form: WalkForwardForm) => void;
}) {
  const [draft, setDraft] = useState(initial);
  useEffect(() => setDraft(initial), [initial]);
  const limits = config.walk_forward;
  const params = useMemo(() => walkForwardParams(draft, config, signals), [draft, config, signals]);
  const runs = walkForwardRuns(draft, params, config);
  const changes = walkForwardChanges(draft, config);
  const invalid =
    hasSetupProblems(draft, config, signals, WALK_FORWARD_PAGE_SECTIONS) ||
    walkForwardBody(draft, params, config) === null;
  const section = config.sections.find((item) => item.name === WALK_FORWARD_SECTION);
  const tooMany = runs !== null && (runs.combinations > config.sweep.max_combinations || runs.runs > limits.max_runs);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!invalid) onSubmit(draft);
  };

  return (
    <Panel>
      <form onSubmit={submit} noValidate className="space-y-4">
        <BacktestSetupFields draft={draft} onChange={setDraft} config={config} signals={signals} outOfSample={false} />
        <SweptParameters
          axes={draft.axes}
          params={params}
          limits={config.sweep}
          canAdd={Boolean(draft.signal)}
          onChange={(axes) => setDraft({ ...draft, axes })}
        />
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Windows</h2>
          <div className="grid gap-x-6 gap-y-4 md:grid-cols-2 lg:grid-cols-3">
            {/* Not a Field: a label around the buttons would press the first one when its text is clicked. */}
            <div className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted">
              <span>In-sample windows</span>
              <Segmented
                label="In-sample windows"
                value={draft.scheme}
                options={SCHEMES}
                onChange={(scheme) => setDraft({ ...draft, scheme })}
              />
              <span className="font-normal">
                {draft.scheme === "rolling"
                  ? "Of fixed length, sliding along with the out-of-sample windows"
                  : "From the first bar, growing with every window"}
              </span>
            </div>
            <Field label="Pick by" hint="Each in-sample window picks the combination with the highest value">
              <Select value={draft.metric} onChange={(event) => setDraft({ ...draft, metric: event.target.value })}>
                {limits.metrics.map((key) => (
                  <option key={key} value={key}>
                    {metricLabel(key)}
                  </option>
                ))}
              </Select>
            </Field>
            {section && (
              <div className="space-y-2">
                <GroupHeading>Windows and picks</GroupHeading>
                <SectionFields
                  section={section}
                  overrides={draft.settings}
                  onChange={(settings) => setDraft({ ...draft, settings })}
                  className="grid grid-cols-2 gap-3"
                />
              </div>
            )}
          </div>
        </section>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className={`num text-sm ${tooMany ? "text-down" : "text-muted"}`}>
            {runs === null
              ? draft.axes.length
                ? "Fix the ranges above."
                : "Pick a parameter to sweep."
              : `${plural(runs.combinations, "combination")} × ${plural(runs.windows, "in-sample window")} = ${plural(runs.runs, "backtest")} (at most ${limits.max_runs}, ${config.sweep.max_combinations} combinations)`}
          </p>
          <div className="flex items-center gap-2">
            {changes > 0 && (
              <Button variant="ghost" onClick={() => setDraft(resetWalkForward(draft, config))}>
                Reset {changes} changed
              </Button>
            )}
            <Button type="submit" variant="primary" disabled={busy || invalid} className="h-9 px-5">
              {busy ? "Running…" : "Run walk-forward"}
            </Button>
          </div>
        </div>
      </form>
    </Panel>
  );
}

function WalkForwardTiles({ result }: { result: WalkForwardOut }) {
  const { metrics: m, unchanged: u } = result;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      <StatTile
        label="Total return"
        value={fmtPct(m.total_return_pct, 1, true)}
        valueClass={tone(m.total_return_pct)}
        sub={`unchanged setup ${fmtPct(u.total_return_pct, 1, true)}`}
      />
      <StatTile
        label="CAGR"
        value={fmtPct(m.cagr_pct, 1, true)}
        sub={`buy & hold ${fmtPct(m.buy_hold_pct, 1, true)} in all`}
      />
      <StatTile label="Sharpe" value={fmtNumber(m.sharpe)} sub={`unchanged setup ${fmtNumber(u.sharpe)}`} />
      <StatTile
        label="Max drawdown"
        value={fmtPct(m.max_drawdown_pct, 1)}
        valueClass="text-down"
        sub={`unchanged setup ${fmtPct(u.max_drawdown_pct, 1)}`}
      />
      <StatTile
        label="Trades"
        value={String(m.trades)}
        sub={`win rate ${fmtPct(m.win_rate_pct, 0)}, ${metricText(m, "expectancy_r")}`}
      />
      <StatTile
        label="Walk-forward efficiency"
        value={result.efficiency === null ? DASH : fmtNumber(result.efficiency)}
        sub={result.efficiency === null ? "the picks did not gain in-sample" : "out-of-sample CAGR / in-sample CAGR"}
      />
    </div>
  );
}

/** A window with its number and the first bar of the window after it (null for the last). */
type WindowRow = WalkForwardWindowOut & { number: number; nextStart: string | null };

/** Whether a window's pick traded other bars than its own: it started late, because a position of the window before was
 * still open, or it ran on, because one of its own was. */
const shifted = (row: WindowRow) =>
  row.traded_from !== row.out_of_sample_start || row.traded_to !== (row.nextStart ?? row.traded_to);

function WindowsTable({ result }: { result: WalkForwardOut }) {
  const label = metricLabel(result.metric);
  const columns = useMemo<Column<WindowRow>[]>(
    () => [
      { key: "number", header: "#", align: "right", render: (row) => String(row.number) },
      { key: "in_sample", header: "In-sample", render: (row) => `${row.in_sample_start} → ${row.in_sample_end}` },
      {
        key: "out_of_sample",
        header: "Out-of-sample",
        render: (row) => `${row.out_of_sample_start} → ${row.out_of_sample_end}`,
      },
      {
        key: "traded",
        header: "Traded",
        title:
          "The bars this window's pick owned: a position still open at a window's end runs to its exit, and the next window trades from there",
        render: (row) =>
          row.traded_from === null ? (
            <span className="text-warn">skipped: the window before was still in a trade</span>
          ) : (
            <span className={shifted(row) ? "text-warn" : undefined}>
              {row.traded_from} → {row.traded_to}
            </span>
          ),
      },
      {
        key: "pick",
        header: "Pick",
        wrap: true,
        render: (row) =>
          row.values ? (
            describeCombination(result.axes, row.values)
          ) : (
            <span className="text-warn">none qualified, held cash</span>
          ),
      },
      {
        key: "qualified",
        header: "Qualified",
        title: `Combinations with a value and at least ${result.walk_forward.min_trades} in-sample trades`,
        align: "right",
        render: (row) => `${row.qualified} of ${result.combinations}`,
      },
      {
        key: "is",
        header: `In-sample ${label}`,
        align: "right",
        render: (row) => metricText(row.in_sample, result.metric),
      },
      {
        key: "oos",
        header: `Out-of-sample ${label}`,
        align: "right",
        render: (row) => metricText(row.out_of_sample, result.metric),
      },
      {
        key: "trades",
        header: "Trades",
        align: "right",
        render: (row) => (row.out_of_sample ? String(row.out_of_sample.trades) : DASH),
      },
      {
        key: "return",
        header: "Return",
        align: "right",
        render: (row) => (
          <span className={tone(row.out_of_sample?.total_return_pct)}>
            {fmtPct(row.out_of_sample?.total_return_pct, 1, true)}
          </span>
        ),
      },
    ],
    [result, label],
  );
  const rows = useMemo(
    () =>
      result.windows.map((window, index) => ({
        ...window,
        number: index + 1,
        nextStart: result.windows[index + 1]?.out_of_sample_start ?? null,
      })),
    [result],
  );
  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => String(row.number)}
      caption="Walk-forward windows"
      dense
    />
  );
}

function windowsCsv(result: WalkForwardOut) {
  return result.windows.map((window, index) => ({
    window: index + 1,
    in_sample_start: window.in_sample_start,
    in_sample_end: window.in_sample_end,
    out_of_sample_start: window.out_of_sample_start,
    out_of_sample_end: window.out_of_sample_end,
    traded_from: window.traded_from,
    traded_to: window.traded_to,
    ...Object.fromEntries(result.axes.map((axis, at) => [axis.key, window.values?.[at] ?? null])),
    qualified: window.qualified,
    ...Object.fromEntries(Object.entries(window.in_sample ?? {}).map(([key, value]) => [`is_${key}`, value])),
    ...Object.fromEntries(Object.entries(window.out_of_sample ?? {}).map(([key, value]) => [`oos_${key}`, value])),
  }));
}

function WalkForwardView({
  result,
  form,
  params,
  config,
}: {
  result: WalkForwardOut;
  form: WalkForwardForm;
  params: SweepParam[];
  config: ConfigOut;
}) {
  const series = useMemo<EquitySeries[]>(
    () => [
      { label: "walk-forward equity", points: result.equity, colorVar: "--accent" },
      { label: "unchanged setup", points: result.unchanged_equity, colorVar: "--warn" },
      {
        label: `${result.ticker} buy & hold`,
        points: result.buy_hold,
        colorVar: "--chart-benchmark",
        dashed: true,
        axis: "left",
      },
    ],
    [result],
  );
  const events = useMemo<EquityEvent[]>(
    () =>
      result.windows.map((window, index) => ({
        time: window.traded_from ?? window.out_of_sample_start,
        text: `W${index + 1}`,
      })),
    [result],
  );
  const label = metricLabel(result.metric);
  const { walk_forward: windows, next } = result;
  const axisParams = result.axes.map((axis) => params.find((param) => param.key === axis.key));
  const few = result.windows.filter((window) => window.in_sample && window.in_sample.trades < MIN_TRADES).length;
  const file = `tradescan-walk-forward-${result.ticker}-${result.signal}`;
  return (
    <div className="space-y-4">
      <div className="space-y-1 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-lg font-semibold">{result.ticker}</span>
          <span className="font-medium">{result.signal}</span>
          <DirectionBadge direction={result.direction} />
          <span className="text-muted">{result.description}</span>
        </div>
        <p className="text-muted">
          {plural(result.combinations, "combination")} on the {result.engine} engine · {windows.windows} {result.scheme}{" "}
          windows of {windows.out_of_sample_bars} bars after in-sample windows of {windows.in_sample_bars} bars
          {result.scheme === "anchored" ? " or more" : ""} · picked by the highest in-sample {label} with at least{" "}
          {plural(windows.min_trades, "trade")}
        </p>
        <p className="text-xs text-muted">
          Each window trades its pick with the equity the window before ended with, and its signal fires only within the
          window. A position still open at a window's end runs to its own exit, and the next window trades from there.
          The unchanged setup trades the same bars with the values as set.
        </p>
      </div>
      {result.errors.length > 0 && (
        <Notice>
          {plural(result.errors.length, "combination")} could not run and were never picked, e.g.{" "}
          {result.errors[0]!.error}
        </Notice>
      )}
      {few > 0 && (
        <Notice>
          {plural(few, "window")} picked a setting with fewer than {MIN_TRADES} in-sample trades: its in-sample metrics
          are mostly noise. Raise the minimum trades or use longer in-sample windows.
        </Notice>
      )}
      <WalkForwardTiles result={result} />
      <Panel>
        <h2 className="mb-2 text-sm font-semibold">
          Out-of-sample equity, {result.out_of_sample_start} → {result.end}
        </h2>
        <EquityChart series={series} events={events} />
      </Panel>
      <section className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Windows</h2>
          <Button onClick={() => downloadCsv(`${file}-windows.csv`, windowsCsv(result))}>Export CSV</Button>
        </div>
        <WindowsTable result={result} />
      </section>
      <section className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">The setting to trade next</h2>
          {next.values && axisParams.every(Boolean) && (
            <Link
              to={`/backtest?${backtestLink(form, axisParams as SweepParam[], next.values, config).toString()}`}
              className="text-sm text-accent hover:underline"
            >
              Open in Backtest →
            </Link>
          )}
        </div>
        <p className="text-sm">
          {next.values ? describeCombination(result.axes, next.values) : "No combination qualified"}
          <span className="text-muted">
            {" "}
            · picked on {next.in_sample_start} → {next.in_sample_end}, in-sample {label}{" "}
            {metricText(next.in_sample, result.metric)}, {next.qualified} of {result.combinations} qualified
          </span>
        </p>
      </section>
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Walk-forward and the unchanged setup</h2>
        <MetricsTable
          columns={[
            { key: "walk-forward", header: "Walk-forward", metrics: result.metrics },
            { key: "unchanged", header: "Unchanged setup", metrics: result.unchanged },
          ]}
          caption="Metrics of the stitched out-of-sample curve and of the unchanged setup on the same bars"
          highlightBest
        />
      </section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{plural(result.trades.length, "out-of-sample trade")}</h2>
        <Button
          onClick={() => downloadCsv(`${file}.csv`, result.trades.map(tradeRow))}
          disabled={!result.trades.length}
        >
          Export CSV
        </Button>
      </div>
      {result.trades.length ? <TradesTable trades={result.trades} /> : <EmptyState title="No window traded" />}
    </div>
  );
}

export function WalkForwardPage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const signals = useSignals();
  const { account } = useAccount();
  const form = useMemo(() => (config.data ? readWalkForwardForm(params, config.data) : null), [params, config.data]);
  const sweepable = useMemo(
    () => (form && config.data && signals.data ? walkForwardParams(form, config.data, signals.data) : []),
    [form, config.data, signals.data],
  );
  const body = useMemo(() => {
    const request = form && config.data && walkForwardBody(form, sweepable, config.data);
    return request ? { ...request, settings: withAccount(request.settings ?? {}, account) } : null;
  }, [form, sweepable, config.data, account]);
  const run = useWalkForward(body);

  if (config.isError || signals.isError) return <ErrorBox error={config.error ?? signals.error} />;
  if (!config.data || !signals.data || !form) return <Loading message="Connecting to the tradescan server…" />;
  const defaults = config.data;

  return (
    <>
      <PageHeader
        title="Walk-forward"
        subtitle="One setup re-tuned on every in-sample window, each pick traded on the window after it, and the out-of-sample windows joined into one curve."
      />
      <WalkForwardFormPanel
        initial={form}
        config={defaults}
        signals={signals.data}
        busy={run.isFetching}
        onSubmit={(next) => setParams(writeWalkForwardForm(next, defaults))}
      />
      {!body && !run.data && (
        <EmptyState title="Choose a setup and up to two parameters">
          Every combination is backtested on each in-sample window; the best one trades the out-of-sample window after
          it.
        </EmptyState>
      )}
      {run.isLoading && <Loading message="Sweeping every in-sample window and trading each pick…" />}
      {run.isError && <ErrorBox error={run.error} onRetry={() => run.refetch()} />}
      {run.data && <WalkForwardView result={run.data} form={form} params={sweepable} config={defaults} />}
    </>
  );
}
