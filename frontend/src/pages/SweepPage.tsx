import { useMemo, type SubmitEvent } from "react";
import { Link, useSearchParams } from "react-router";

import type { ConfigOut, SignalOut, SweepCellOut, SweepOut } from "../api/client";
import { useConfig, useSignals, useSweep } from "../api/hooks";
import { METRICS } from "../components/BacktestResults";
import { BacktestSetupFields } from "../components/BacktestSetupFields";
import { describeSplit, PERIOD_NOTE } from "../components/OutOfSample";
import { CombinationCount, SweptParameters } from "../components/SweepAxisFields";
import { SweepResults } from "../components/SweepResults";
import { Button, DirectionBadge, EmptyState, ErrorBox, Loading, PageHeader, Panel } from "../components/ui";
import { type MetricKey } from "../lib/compare";
import { writeBacktestForm } from "../lib/params";
import { hasSetupProblems, resetSetup, setupChanges } from "../lib/setup";
import {
  axisRanges,
  DEFAULT_METRIC,
  readSweepForm,
  sweepBody,
  sweepParams,
  withCombination,
  writeSweepForm,
  type SweepForm,
  type SweepParam,
} from "../lib/sweep";
import { useResettableState } from "../lib/useResettableState";
import { useAccount, withAccount } from "../state/account";

const METRIC_KEYS = new Set<string>(METRICS.map((metric) => metric.key));
const readMetric = (value: string | null): MetricKey =>
  value && METRIC_KEYS.has(value) ? (value as MetricKey) : DEFAULT_METRIC;

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

function SweepFormPanel({
  initial,
  config,
  signals,
  busy,
  onSubmit,
}: {
  initial: SweepForm;
  config: ConfigOut;
  signals: SignalOut[];
  busy: boolean;
  onSubmit: (form: SweepForm) => void;
}) {
  const [draft, setDraft] = useResettableState(initial);
  const limits = config.sweep;
  const params = useMemo(() => sweepParams(draft, config, signals), [draft, config, signals]);
  const ranges = axisRanges(draft.axes, params, limits);
  const changes = setupChanges(draft, config);
  const invalid = hasSetupProblems(draft, config, signals) || sweepBody(draft, params, limits) === null;

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (!invalid) onSubmit(draft);
  };

  return (
    <Panel>
      <form onSubmit={submit} noValidate className="space-y-4">
        <BacktestSetupFields draft={draft} onChange={setDraft} config={config} signals={signals} />
        <SweptParameters
          axes={draft.axes}
          params={params}
          limits={limits}
          canAdd={Boolean(draft.signal)}
          onChange={(axes) => setDraft({ ...draft, axes })}
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CombinationCount ranges={ranges} limits={limits} />
          <div className="flex items-center gap-2">
            {changes > 0 && (
              <Button variant="ghost" onClick={() => setDraft(resetSetup(draft, config))}>
                Reset {changes} changed
              </Button>
            )}
            <Button type="submit" variant="primary" disabled={busy || invalid} className="h-9 px-5">
              {busy ? "Running…" : "Run sweep"}
            </Button>
          </div>
        </div>
      </form>
    </Panel>
  );
}

function SweepView({
  result,
  form,
  params,
  metric,
  onMetric,
  config,
}: {
  result: SweepOut;
  form: SweepForm;
  params: SweepParam[];
  metric: MetricKey;
  onMetric: (metric: MetricKey) => void;
  config: ConfigOut;
}) {
  const axisParams = result.axes.map((axis) => params.find((param) => param.key === axis.key));
  const open = (cell: SweepCellOut) =>
    axisParams.every(Boolean) ? (
      <Link
        to={`/backtest?${writeBacktestForm({ ...withCombination(form, axisParams as SweepParam[], cell.values), engines: [result.engine] }, config).toString()}`}
        className="text-sm text-accent hover:underline"
      >
        Open in Backtest →
      </Link>
    ) : null;

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
          {plural(result.cells.length, "combination")} on the {result.engine} engine · {describeSplit(result.split)}
        </p>
        <p className="text-xs text-muted">{PERIOD_NOTE}</p>
      </div>
      <SweepResults
        split={result.split}
        axes={result.axes}
        cells={result.cells}
        metric={metric}
        onMetric={onMetric}
        open={open}
      />
    </div>
  );
}

export function SweepPage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const signals = useSignals();
  const { account } = useAccount();
  const form = useMemo(() => (config.data ? readSweepForm(params, config.data) : null), [params, config.data]);
  const metric = readMetric(params.get("m"));
  const sweepable = useMemo(
    () => (form && config.data && signals.data ? sweepParams(form, config.data, signals.data) : []),
    [form, config.data, signals.data],
  );
  const body = useMemo(() => {
    const request = form && config.data && sweepBody(form, sweepable, config.data.sweep);
    return request ? { ...request, settings: withAccount(request.settings ?? {}, account) } : null;
  }, [form, sweepable, config.data, account]);
  const sweep = useSweep(body);

  if (config.isError || signals.isError) return <ErrorBox error={config.error ?? signals.error} />;
  if (!config.data || !signals.data || !form) return <Loading message="Connecting to the tradescan server…" />;
  const defaults = config.data;

  const withMetric = (next: URLSearchParams, value: MetricKey) => {
    if (value !== DEFAULT_METRIC) next.set("m", value);
    return next;
  };

  return (
    <>
      <PageHeader
        title="Sweep"
        subtitle="One setup over a range of one or two parameters. The out-of-sample heatmap shows whether a good setting holds on history it was not tuned on."
      />
      <SweepFormPanel
        initial={form}
        config={defaults}
        signals={signals.data}
        busy={sweep.isFetching}
        onSubmit={(next) => setParams(withMetric(writeSweepForm(next, defaults), metric))}
      />
      {!body && !sweep.data && (
        <EmptyState title="Choose a setup and up to two parameters">
          Every combination is backtested on the first part of the history and checked on the last part. At most{" "}
          {defaults.sweep.max_combinations} combinations per sweep.
        </EmptyState>
      )}
      {sweep.isLoading && <Loading message="Running every combination in-sample and out-of-sample…" />}
      {sweep.isError && <ErrorBox error={sweep.error} onRetry={() => void sweep.refetch()} />}
      {sweep.data && (
        <SweepView
          result={sweep.data}
          form={form}
          params={sweepable}
          metric={metric}
          onMetric={(value) => setParams(withMetric(writeSweepForm(form, defaults), value), { replace: true })}
          config={defaults}
        />
      )}
    </>
  );
}
