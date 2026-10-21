import { useMemo, type SubmitEvent } from "react";
import { Link, useSearchParams } from "react-router";

import type { ConfigOut, RotationSweepCellOut, RotationSweepOut, WatchlistOut } from "../api/client";
import { useConfig, useRotationSweep, useWatchlists } from "../api/hooks";
import { METRICS } from "../components/BacktestResults";
import { describeSplit } from "../components/OutOfSample";
import { RotationSetupFields } from "../components/RotationSetupFields";
import { RotationStatsTable } from "../components/RotationStats";
import { CombinationCount, SweptParameters } from "../components/SweepAxisFields";
import { SweepResults } from "../components/SweepResults";
import { Button, EmptyState, ErrorBox, Loading, Notice, PageHeader, Panel } from "../components/ui";
import { LARGE_UNIVERSE, universeSize, withDefaultUniverse } from "../lib/choices";
import { type MetricKey } from "../lib/compare";
import { hasRotationProblems, resetRotation, rotationChanges, writeRotationForm } from "../lib/rotation";
import {
  readRotationSweepForm,
  rotationSweepBody,
  rotationSweepParams,
  withRotationCombination,
  writeRotationSweepForm,
  type RotationSweepForm,
  type RotationSweepParam,
} from "../lib/rotationSweep";
import { axisRanges, DEFAULT_METRIC } from "../lib/sweep";
import { useResettableState } from "../lib/useResettableState";
import { useAccount, withAccount } from "../state/account";

const METRIC_KEYS = new Set<string>(METRICS.map((metric) => metric.key));
const readMetric = (value: string | null): MetricKey =>
  value && METRIC_KEYS.has(value) ? (value as MetricKey) : DEFAULT_METRIC;

/** Above this many tickers, each combination takes about a second. */
const SLOW_TICKERS = 50;

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

const PERIOD_NOTE =
  "Each period starts with fresh equity; the out-of-sample run rebalances from the split on, with its lookbacks already warm. A holding has no stop, so it has no R multiple.";

function RotationSweepFormPanel({
  initial,
  config,
  watchlists,
  busy,
  onSubmit,
}: {
  initial: RotationSweepForm;
  config: ConfigOut;
  watchlists: WatchlistOut[];
  busy: boolean;
  onSubmit: (form: RotationSweepForm) => void;
}) {
  const source = useMemo(() => withDefaultUniverse(initial, watchlists), [initial, watchlists]);
  const [draft, setDraft] = useResettableState(source);
  const limits = config.rotation_sweep;
  const params = useMemo(() => rotationSweepParams(draft, config), [draft, config]);
  const ranges = axisRanges(draft.axes, params, limits);
  const changes = rotationChanges(draft, config);
  const invalid = hasRotationProblems(draft, config) || rotationSweepBody(draft, params, limits) === null;
  const slow = draft.axes.length > 0 && universeSize(draft.universe, watchlists) > SLOW_TICKERS;

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (!invalid) onSubmit(draft);
  };

  return (
    <Panel>
      <form onSubmit={submit} noValidate className="space-y-4">
        <RotationSetupFields draft={draft} onChange={setDraft} config={config} watchlists={watchlists} />
        <SweptParameters
          axes={draft.axes}
          params={params}
          limits={limits}
          canAdd={params.length > 0}
          onChange={(axes) => setDraft({ ...draft, axes })}
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CombinationCount ranges={ranges} limits={limits} />
          <div className="flex items-center gap-2">
            {changes > 0 && (
              <Button variant="ghost" onClick={() => setDraft({ ...draft, ...resetRotation(draft, config) })}>
                Reset {changes} changed
              </Button>
            )}
            <Button type="submit" variant="primary" disabled={busy || invalid} className="h-9 px-5">
              {busy ? "Running…" : "Run sweep"}
            </Button>
          </div>
        </div>
        {slow && (
          <Notice>
            Every combination runs the rotation on the whole watchlist twice, in-sample and out-of-sample: expect about
            a second per combination for 100 tickers of 10-year history, twice that when rebalancing weekly.
          </Notice>
        )}
      </form>
    </Panel>
  );
}

function RotationSweepView({
  result,
  form,
  params,
  metric,
  onMetric,
  config,
}: {
  result: RotationSweepOut;
  form: RotationSweepForm;
  params: RotationSweepParam[];
  metric: MetricKey;
  onMetric: (metric: MetricKey) => void;
  config: ConfigOut;
}) {
  const { rotation } = result;
  const axisParams = result.axes.map((axis) => params.find((param) => param.key === axis.key));
  const open = (cell: RotationSweepCellOut) => {
    if (!axisParams.every(Boolean)) return null;
    const { axes: _axes, ...setup } = form;
    const combination = withRotationCombination(setup, axisParams as RotationSweepParam[], cell.values);
    return (
      <Link
        to={`/rotation?${writeRotationForm(combination, config).toString()}`}
        className="text-sm text-accent hover:underline"
      >
        Open in Rotation →
      </Link>
    );
  };
  const details = (cell: RotationSweepCellOut) => (
    <RotationStatsTable
      caption="Rotation stats of the selected combination in both periods"
      columns={[
        { key: "in", header: "In-sample", stats: cell.in_sample_stats },
        { key: "out", header: "Out-of-sample", stats: cell.out_of_sample_stats },
      ]}
    />
  );

  return (
    <div className="space-y-4">
      <div className="space-y-1 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-lg font-semibold">{result.universe}</span>
          <span className="font-medium">
            top {rotation.holdings}, rebalanced {rotation.rebalance}
          </span>
        </div>
        <p className="text-muted">
          Ranking: {result.ranking.description} · weights: {result.weighting.description}
        </p>
        <p className="text-muted">
          {plural(result.cells.length, "combination")} on the {result.engine} engine · {describeSplit(result.split)} ·
          buy & hold is {result.buy_hold_benchmark}'s
        </p>
        <p className="text-xs text-muted">{PERIOD_NOTE}</p>
      </div>
      {result.missing.length > 0 && <Notice>No data for: {result.missing.join(", ")}</Notice>}
      <SweepResults
        split={result.split}
        axes={result.axes}
        cells={result.cells}
        metric={metric}
        onMetric={onMetric}
        open={open}
        details={details}
      />
    </div>
  );
}

export function RotationSweepPage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const watchlists = useWatchlists();
  const { account } = useAccount();
  // The rules a link leaves out are the server's defaults, so the form needs the config first.
  const form = useMemo(() => (config.data ? readRotationSweepForm(params, config.data) : null), [params, config.data]);
  const metric = readMetric(params.get("m"));
  const sweepable = useMemo(
    () => (form && config.data ? rotationSweepParams(form, config.data) : []),
    [form, config.data],
  );
  const body = useMemo(() => {
    const request = form && config.data && rotationSweepBody(form, sweepable, config.data.rotation_sweep);
    return request ? { ...request, settings: withAccount(request.settings ?? {}, account) } : null;
  }, [form, sweepable, config.data, account]);
  const sweep = useRotationSweep(body);

  const failed = config.error ?? watchlists.error;
  if (failed) return <ErrorBox error={failed} />;
  if (!config.data || !watchlists.data || !form) return <Loading message="Connecting to the tradescan server…" />;
  const defaults = config.data;

  const withMetric = (next: URLSearchParams, value: MetricKey) => {
    if (value !== DEFAULT_METRIC) next.set("m", value);
    return next;
  };

  return (
    <>
      <PageHeader
        title="Rotation sweep"
        subtitle="One rotation over a range of one or two of its parameters. The out-of-sample heatmap shows whether a good setting holds on history it was not tuned on."
      />
      <RotationSweepFormPanel
        initial={form}
        config={defaults}
        watchlists={watchlists.data}
        busy={sweep.isFetching}
        onSubmit={(next) => setParams(withMetric(writeRotationSweepForm(next, defaults), metric))}
      />
      {!body && !sweep.data && (
        <EmptyState title="Choose a watchlist and up to two parameters">
          Every combination runs on the first part of the history and is checked on the last part. At most{" "}
          {defaults.rotation_sweep.max_combinations} combinations per sweep.
        </EmptyState>
      )}
      {sweep.isLoading && (
        <Loading
          message={
            universeSize(form.universe, watchlists.data) > LARGE_UNIVERSE
              ? "Running every combination on a large universe… The first run downloads every ticker."
              : "Running every combination in-sample and out-of-sample…"
          }
        />
      )}
      {sweep.isError && <ErrorBox error={sweep.error} onRetry={() => void sweep.refetch()} />}
      {sweep.data && (
        <RotationSweepView
          result={sweep.data}
          form={form}
          params={sweepable}
          metric={metric}
          onMetric={(value) => setParams(withMetric(writeRotationSweepForm(form, defaults), value), { replace: true })}
          config={defaults}
        />
      )}
    </>
  );
}
