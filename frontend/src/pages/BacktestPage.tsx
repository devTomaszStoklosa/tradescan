import { useMemo, type SubmitEvent } from "react";
import { Link, useSearchParams } from "react-router";

import type { BacktestOut, ConfigOut, SignalOut } from "../api/client";
import { useBacktest, useChart, useConfig, useSignals } from "../api/hooks";
import { KeyMetrics, MetricsComparison, TradesTable } from "../components/BacktestResults";
import { BacktestSetupFields } from "../components/BacktestSetupFields";
import { EquityChart, type EquityEvent, type EquitySeries } from "../components/charts/EquityChart";
import { PriceChart, type ChartMarker } from "../components/charts/PriceChart";
import { MonteCarloPanel } from "../components/MonteCarlo";
import { PeriodsPanel } from "../components/OutOfSample";
import { SectionFields } from "../components/ParamFields";
import { PinRunButton } from "../components/PinRunButton";
import {
  Button,
  DirectionBadge,
  EmptyState,
  ErrorBox,
  Field,
  Loading,
  PageHeader,
  Panel,
  Segmented,
  ToggleChip,
} from "../components/ui";
import { BACKTEST_PAGE_SECTIONS, MONTE_CARLO_SECTION } from "../lib/choices";
import { downloadCsv, tradeRow } from "../lib/csv";
import { fmtNumber } from "../lib/format";
import { backtestBody, readBacktestForm, writeBacktestForm, type BacktestForm } from "../lib/params";
import { hasSetupProblems, resetSetup, setupChanges } from "../lib/setup";
import { newSweepForm, writeSweepForm } from "../lib/sweep";
import { useResettableState } from "../lib/useResettableState";
import { useAccount, withAccount } from "../state/account";

const ENGINE_COLORS = ["--accent", "--warn"];

function BacktestFormPanel({
  initial,
  config,
  signals,
  busy,
  onSubmit,
}: {
  initial: BacktestForm;
  config: ConfigOut;
  signals: SignalOut[];
  busy: boolean;
  onSubmit: (form: BacktestForm) => void;
}) {
  const [draft, setDraft] = useResettableState(initial);
  const toggleEngine = (engine: string) =>
    setDraft({
      ...draft,
      engines: draft.engines.includes(engine)
        ? draft.engines.filter((item) => item !== engine)
        : [...draft.engines, engine],
    });
  const changes = setupChanges(draft, config);
  const invalid = !draft.engines.length || hasSetupProblems(draft, config, signals, BACKTEST_PAGE_SECTIONS);
  const monteCarlo = config.sections.find((section) => section.name === MONTE_CARLO_SECTION);

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (!invalid) onSubmit(draft);
  };

  return (
    <Panel>
      <form onSubmit={submit} noValidate className="space-y-4">
        <BacktestSetupFields draft={draft} onChange={setDraft} config={config} signals={signals} />
        {monteCarlo && (
          <section className="space-y-2">
            <h2 className="text-sm font-semibold">Monte Carlo of the trades</h2>
            <SectionFields
              section={monteCarlo}
              overrides={draft.settings}
              onChange={(settings) => setDraft({ ...draft, settings })}
            />
          </section>
        )}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <Field label="Engines">
            <div className="flex gap-1.5 py-1">
              {config.engines.map((engine) => (
                <ToggleChip
                  key={engine}
                  active={draft.engines.includes(engine)}
                  onClick={() => toggleEngine(engine)}
                  color="var(--accent)"
                >
                  {engine}
                </ToggleChip>
              ))}
            </div>
          </Field>
          <div className="flex items-center gap-2">
            {changes > 0 && (
              <Button variant="ghost" onClick={() => setDraft(resetSetup(draft, config))}>
                Reset {changes} changed
              </Button>
            )}
            <Button type="submit" variant="primary" disabled={busy || invalid} className="h-9 px-5">
              {busy ? "Running…" : "Run backtest"}
            </Button>
          </div>
        </div>
      </form>
    </Panel>
  );
}

function BacktestView({ result, form, config }: { result: BacktestOut; form: BacktestForm; config: ConfigOut }) {
  // A new result shows its first engine.
  const [engine, setEngine] = useResettableState(result.runs[0]?.engine ?? "", result);
  const run = result.runs.find((item) => item.engine === engine) ?? result.runs[0];
  const chartBody = useMemo(() => ({ ticker: result.ticker }), [result.ticker]);
  const chart = useChart(chartBody);

  const equitySeries = useMemo<EquitySeries[]>(
    () => [
      ...result.runs.map((item, index) => ({
        label: `${item.engine} equity`,
        points: item.equity,
        colorVar: ENGINE_COLORS[index % ENGINE_COLORS.length] ?? "--accent",
        dashed: index > 0,
      })),
      { label: "buy & hold", points: result.buy_hold, colorVar: "--chart-benchmark", dashed: true, axis: "left" },
    ],
    [result],
  );

  const splitEvents = useMemo<EquityEvent[]>(
    () => (result.split ? [{ time: result.split.out_of_sample_start, text: "out-of-sample" }] : []),
    [result.split],
  );

  const markers = useMemo<ChartMarker[]>(() => {
    if (!run) return [];
    const long = result.direction === "long";
    return run.trades.flatMap((trade): ChartMarker[] => [
      {
        time: trade.entry_date,
        position: long ? "belowBar" : "aboveBar",
        shape: long ? "arrowUp" : "arrowDown",
        tone: "accent",
      },
      ...trade.adds.map((fill): ChartMarker => ({
        time: fill.date,
        position: long ? "belowBar" : "aboveBar",
        shape: long ? "arrowUp" : "arrowDown",
        tone: "accent",
        text: "+",
      })),
      {
        time: trade.exit_date,
        position: long ? "aboveBar" : "belowBar",
        shape: "circle",
        tone: trade.pnl >= 0 ? "up" : "down",
      },
    ]);
  }, [run, result.direction]);

  if (!run) return null;
  const used = result.config;
  const exits = result.exits.map((exit) => exit.description).join("; ") || "none, only the stop";
  const filters = result.filters.map((filter) => filter.description).join("; ");
  return (
    <div className="space-y-4">
      <div className="space-y-1 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-lg font-semibold">{result.ticker}</span>
          <span className="font-medium">{result.signal}</span>
          <DirectionBadge direction={result.direction} />
          <span className="text-muted">{result.description}</span>
          <div className="ml-auto">
            <PinRunButton result={result} engine={run.engine} form={form} />
          </div>
        </div>
        <p className="text-muted">
          {result.start} → {result.end} · risk {fmtNumber(used.risk_pct, 2)}%, max position{" "}
          {fmtNumber(used.max_position_pct, 0)}% · costs {fmtNumber(used.commission_pct, 2)}% +{" "}
          {fmtNumber(used.slippage_pct, 2)}%
        </p>
        {filters && (
          <p className="text-muted">
            Filters: {filters}
            {result.benchmark && ` · benchmark ${result.benchmark}`}
          </p>
        )}
        <p className="text-muted">
          Entry: {result.entry.description} · initial stop {fmtNumber(used.atr_mult, 2)} × ATR({used.atr_period})
          {used.max_units > 1 &&
            ` · pyramiding up to ${used.max_units} units ${fmtNumber(used.add_every_atr, 2)} ATR apart`}{" "}
          · exits: {exits}
        </p>
        <Link
          to={`/sweep?${writeSweepForm(newSweepForm(form), config).toString()}`}
          className="inline-block text-accent hover:underline"
        >
          Sweep parameters of this setup →
        </Link>
      </div>
      {result.runs.length > 1 && (
        <Segmented
          label="Engine"
          value={engine}
          onChange={setEngine}
          options={result.runs.map((item) => ({ value: item.engine, label: item.engine }))}
        />
      )}
      <KeyMetrics run={run} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel>
          <h2 className="mb-2 text-sm font-semibold">Equity</h2>
          <EquityChart series={equitySeries} events={splitEvents} />
        </Panel>
        <MetricsComparison result={result} />
      </div>
      <PeriodsPanel run={run} split={result.split} start={result.start} end={result.end} />
      <MonteCarloPanel run={run} />
      <Panel>
        <h2 className="mb-2 text-sm font-semibold">Trades on the chart</h2>
        {chart.isLoading && <Loading message="Loading chart…" />}
        {chart.isError && <ErrorBox error={chart.error} onRetry={() => void chart.refetch()} />}
        {chart.data && (
          <PriceChart
            label={`${result.ticker} with ${result.signal} trades`}
            candles={chart.data.candles}
            smaFast={chart.data.sma_fast}
            smaSlow={chart.data.sma_slow}
            markers={markers}
            visibleBars={260}
          />
        )}
      </Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">
          {run.trades.length} trades ({run.engine})
        </h2>
        <Button
          onClick={() =>
            downloadCsv(`tradescan-${result.ticker}-${result.signal}-${run.engine}.csv`, run.trades.map(tradeRow))
          }
          disabled={!run.trades.length}
        >
          Export CSV
        </Button>
      </div>
      {run.trades.length ? (
        <TradesTable trades={run.trades} />
      ) : (
        <EmptyState title="The signal never triggered a trade in this period" />
      )}
    </div>
  );
}

export function BacktestPage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const signals = useSignals();
  const { account } = useAccount();
  // The rules a link leaves out are the server's defaults, so the form needs the config first.
  const form = useMemo(() => (config.data ? readBacktestForm(params, config.data) : null), [params, config.data]);
  const body = useMemo(() => {
    const request = form && backtestBody(form);
    return form && request ? { ...request, settings: withAccount(form.settings, account) } : null;
  }, [form, account]);
  const backtest = useBacktest(body);

  if (config.isError || signals.isError) return <ErrorBox error={config.error ?? signals.error} />;
  if (!config.data || !signals.data || !form) return <Loading message="Connecting to the tradescan server…" />;
  const defaults = config.data;

  return (
    <>
      <PageHeader
        title="Backtest"
        subtitle="One signal on one ticker with the entry and exit rules you choose. Every parameter is adjustable."
      />
      <BacktestFormPanel
        initial={form}
        config={config.data}
        signals={signals.data}
        busy={backtest.isFetching}
        onSubmit={(next) => setParams(writeBacktestForm(next, defaults))}
      />
      {!body && (
        <EmptyState title="Choose a ticker and a signal">
          Select both engines to check that the pandas engine matches backtrader's Cerebro.
        </EmptyState>
      )}
      {backtest.isLoading && <Loading message="Downloading history and running the backtest…" />}
      {backtest.isError && <ErrorBox error={backtest.error} onRetry={() => void backtest.refetch()} />}
      {backtest.data && <BacktestView result={backtest.data} form={form} config={defaults} />}
    </>
  );
}
