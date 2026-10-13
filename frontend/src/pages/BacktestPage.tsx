import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";

import type { BacktestOut, ConfigOut, SignalOut } from "../api/client";
import { useBacktest, useChart, useConfig, useSignals } from "../api/hooks";
import { KeyMetrics, MetricsComparison, TradesTable } from "../components/BacktestResults";
import { EquityChart, type EquitySeries } from "../components/charts/EquityChart";
import { PriceChart, type ChartMarker } from "../components/charts/PriceChart";
import { FAMILY_LABELS } from "../components/SignalChip";
import { Button, DirectionBadge, EmptyState, ErrorBox, Field, Input, Loading, NumberInput, PageHeader, Panel, Segmented, Select, ToggleChip } from "../components/ui";
import { PERIODS } from "../lib/choices";
import { downloadCsv } from "../lib/csv";
import { fmtNumber } from "../lib/format";
import { backtestBody, readBacktestForm, writeBacktestForm, type BacktestForm } from "../lib/params";
import { toAccountIn, useAccount } from "../state/account";

const ENGINE_COLORS = ["--accent", "--warn"];

function SignalSelect({ value, onChange, signals }: { value: string; onChange: (value: string) => void; signals: SignalOut[] }) {
  const groups = useMemo(() => {
    const byFamily = new Map<string, SignalOut[]>();
    for (const signal of signals) byFamily.set(signal.family, [...(byFamily.get(signal.family) ?? []), signal]);
    return [...byFamily.entries()];
  }, [signals]);
  return (
    <Select value={value} onChange={(event) => onChange(event.target.value)} required>
      <option value="" disabled>
        Choose a signal…
      </option>
      {groups.map(([family, items]) => (
        <optgroup key={family} label={FAMILY_LABELS[family as SignalOut["family"]]}>
          {items.map((signal) => (
            <option key={signal.name} value={signal.name} title={signal.description}>
              {signal.name} ({signal.direction})
            </option>
          ))}
        </optgroup>
      ))}
    </Select>
  );
}

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
  const [draft, setDraft] = useState(initial);
  useEffect(() => setDraft(initial), [initial]);
  const defaults = config.backtest;
  const set = <K extends keyof BacktestForm>(key: K, value: BacktestForm[K]) => setDraft({ ...draft, [key]: value });
  const toggleEngine = (engine: string) =>
    set("engines", draft.engines.includes(engine) ? draft.engines.filter((item) => item !== engine) : [...draft.engines, engine]);
  const description = signals.find((signal) => signal.name === draft.signal)?.description;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (backtestBody(draft)) onSubmit(draft);
  };

  return (
    <Panel>
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-[10rem_minmax(0,1fr)_8rem]">
          <Field label="Ticker">
            <Input value={draft.ticker} placeholder="SPY" required onChange={(event) => set("ticker", event.target.value.toUpperCase())} />
          </Field>
          <Field label="Signal" hint={description}>
            <SignalSelect value={draft.signal} onChange={(value) => set("signal", value)} signals={signals} />
          </Field>
          <Field label="History">
            <Select value={draft.period} onChange={(event) => set("period", event.target.value)}>
              <option value="">default ({defaults.period})</option>
              {PERIODS.map((period) => (
                <option key={period} value={period}>
                  {period}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Field label="Stop (ATR ×)">
            <NumberInput value={draft.atrMult} min={0} step="0.25" placeholder={fmtNumber(defaults.atr_mult, 2)} onChange={(value) => set("atrMult", value)} />
          </Field>
          <Field label="Target (R)">
            <NumberInput value={draft.targetR} min={0} step="0.25" placeholder={fmtNumber(defaults.target_r, 2)} onChange={(value) => set("targetR", value)} />
          </Field>
          <Field label="Max hold (bars)">
            <NumberInput value={draft.maxHold} min={1} step="1" placeholder={String(defaults.max_hold_bars)} onChange={(value) => set("maxHold", value)} />
          </Field>
          <Field label="Commission %">
            <NumberInput value={draft.commissionPct} min={0} step="0.01" placeholder={fmtNumber(defaults.commission_pct, 2)} onChange={(value) => set("commissionPct", value)} />
          </Field>
          <Field label="Slippage %">
            <NumberInput value={draft.slippagePct} min={0} step="0.01" placeholder={fmtNumber(defaults.slippage_pct, 2)} onChange={(value) => set("slippagePct", value)} />
          </Field>
        </div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <Field label="Engines">
            <div className="flex gap-1.5 py-1">
              {config.engines.map((engine) => (
                <ToggleChip key={engine} active={draft.engines.includes(engine)} onClick={() => toggleEngine(engine)} color="var(--accent)">
                  {engine}
                </ToggleChip>
              ))}
            </div>
          </Field>
          <Button type="submit" variant="primary" disabled={busy || !backtestBody(draft)} className="h-9 px-5">
            {busy ? "Running…" : "Run backtest"}
          </Button>
        </div>
      </form>
    </Panel>
  );
}

function BacktestView({ result }: { result: BacktestOut }) {
  const [engine, setEngine] = useState(result.runs[0]?.engine ?? "");
  useEffect(() => setEngine(result.runs[0]?.engine ?? ""), [result]);
  const run = result.runs.find((item) => item.engine === engine) ?? result.runs[0];
  const chart = useChart(result.ticker, [], undefined);

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

  const markers = useMemo<ChartMarker[]>(() => {
    if (!run) return [];
    const long = result.direction === "long";
    return run.trades.flatMap((trade): ChartMarker[] => [
      { time: trade.entry_date, position: long ? "belowBar" : "aboveBar", shape: long ? "arrowUp" : "arrowDown", tone: "accent" },
      { time: trade.exit_date, position: long ? "aboveBar" : "belowBar", shape: "circle", tone: trade.pnl >= 0 ? "up" : "down" },
    ]);
  }, [run, result.direction]);

  if (!run) return null;
  const { config } = result;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-mono text-lg font-semibold">{result.ticker}</span>
        <span className="font-medium">{result.signal}</span>
        <DirectionBadge direction={result.direction} />
        <span className="text-muted">
          {result.start} → {result.end} · stop {fmtNumber(config.atr_mult, 2)} ATR · target {fmtNumber(config.target_r, 2)}R · time exit{" "}
          {config.max_hold_bars} bars · risk {fmtNumber(config.risk_pct, 2)}% · costs {fmtNumber(config.commission_pct, 2)}% +{" "}
          {fmtNumber(config.slippage_pct, 2)}%
        </span>
      </div>
      {result.runs.length > 1 && (
        <Segmented label="Engine" value={engine} onChange={setEngine} options={result.runs.map((item) => ({ value: item.engine, label: item.engine }))} />
      )}
      <KeyMetrics run={run} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel>
          <h2 className="mb-2 text-sm font-semibold">Equity</h2>
          <EquityChart series={equitySeries} />
        </Panel>
        <MetricsComparison result={result} />
      </div>
      <Panel>
        <h2 className="mb-2 text-sm font-semibold">Trades on the chart</h2>
        {chart.isLoading && <Loading message="Loading chart…" />}
        {chart.isError && <ErrorBox error={chart.error} onRetry={() => chart.refetch()} />}
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
          onClick={() => downloadCsv(`tradescan-${result.ticker}-${result.signal}-${run.engine}.csv`, run.trades.map((trade) => ({ ...trade })))}
          disabled={!run.trades.length}
        >
          Export CSV
        </Button>
      </div>
      {run.trades.length ? <TradesTable trades={run.trades} /> : <EmptyState title="The signal never triggered a trade in this period" />}
    </div>
  );
}

export function BacktestPage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const signals = useSignals();
  const { account } = useAccount();
  const form = useMemo(() => readBacktestForm(params), [params]);
  const body = useMemo(() => {
    const request = backtestBody(form);
    return request ? { ...request, account: toAccountIn(account) } : null;
  }, [form, account]);
  const backtest = useBacktest(body);

  if (config.isError || signals.isError) return <ErrorBox error={config.error ?? signals.error} />;
  if (!config.data || !signals.data) return <Loading message="Connecting to the tradescan server…" />;

  return (
    <>
      <PageHeader title="Backtest" subtitle="One signal on one ticker: next-open entries, ATR stop, R-multiple target, time exit." />
      <BacktestFormPanel
        initial={form}
        config={config.data}
        signals={signals.data}
        busy={backtest.isFetching}
        onSubmit={(next) => setParams(writeBacktestForm(next))}
      />
      {!body && (
        <EmptyState title="Choose a ticker and a signal">Select both engines to check that the pandas engine matches backtrader's Cerebro.</EmptyState>
      )}
      {backtest.isLoading && <Loading message="Downloading history and running the backtest…" />}
      {backtest.isError && <ErrorBox error={backtest.error} onRetry={() => backtest.refetch()} />}
      {backtest.data && <BacktestView result={backtest.data} />}
    </>
  );
}
