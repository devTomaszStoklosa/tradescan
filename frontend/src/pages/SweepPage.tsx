import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import type { ConfigOut, SignalOut, SweepOut } from "../api/client";
import { useConfig, useSignals, useSweep } from "../api/hooks";
import { METRICS, MetricsTable } from "../components/BacktestResults";
import { BacktestSetupFields } from "../components/BacktestSetupFields";
import { describeSplit, PERIOD_NOTE } from "../components/OutOfSample";
import { cellText, describeCombination, formatValue, SweepHeatmap, SweepLegend } from "../components/SweepHeatmap";
import { Button, DirectionBadge, EmptyState, ErrorBox, Field, Loading, Notice, NumberInput, PageHeader, Panel, Select, StatTile } from "../components/ui";
import { MIN_TRADES, type MetricKey } from "../lib/compare";
import { DASH, fmtNumber, fmtPct } from "../lib/format";
import { writeBacktestForm } from "../lib/params";
import { hasSetupProblems, resetSetup, setupChanges } from "../lib/setup";
import {
  aboveBreakEven,
  axisValues,
  bestCell,
  cellValue,
  combinations,
  defaultAxis,
  DEFAULT_METRIC,
  heatScale,
  median,
  neighbourAverage,
  periodValues,
  readSweepForm,
  sweepBody,
  sweepParams,
  withCombination,
  writeSweepForm,
  type AxisForm,
  type Period,
  type SweepForm,
  type SweepParam,
} from "../lib/sweep";
import { useAccount, withAccount } from "../state/account";

const METRIC_KEYS = new Set<string>(METRICS.map((metric) => metric.key));
const readMetric = (value: string | null): MetricKey => (value && METRIC_KEYS.has(value) ? (value as MetricKey) : DEFAULT_METRIC);

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

function ParamSelect({ value, params, used, onChange, label }: { value: string; params: SweepParam[]; used: string[]; onChange: (key: string) => void; label: string }) {
  const groups = useMemo(() => {
    const byGroup = new Map<string, SweepParam[]>();
    for (const param of params) byGroup.set(param.group, [...(byGroup.get(param.group) ?? []), param]);
    return [...byGroup.entries()];
  }, [params]);
  const known = params.some((param) => param.key === value);
  return (
    <Select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      {!known && <option value={value}>{value ? `${value} (not in this setup)` : "Choose a parameter…"}</option>}
      {groups.map(([group, items]) => (
        <optgroup key={group} label={group}>
          {items.map((param) => (
            <option key={param.key} value={param.key} disabled={used.includes(param.key) && param.key !== value}>
              {param.spec.unit ? `${param.spec.label} (${param.spec.unit})` : param.spec.label}
            </option>
          ))}
        </optgroup>
      ))}
    </Select>
  );
}

function AxisFields({
  position,
  axis,
  params,
  used,
  limits,
  onChange,
  onRemove,
}: {
  position: number;
  axis: AxisForm;
  params: SweepParam[];
  used: string[];
  limits: ConfigOut["sweep"];
  onChange: (axis: AxisForm) => void;
  onRemove: () => void;
}) {
  const param = params.find((item) => item.key === axis.key);
  const range = param ? axisValues(axis, param.spec, limits) : null;
  const set = (key: "from" | "to" | "step") => (value: number | null) => onChange({ ...axis, [key]: value });
  const name = `Parameter ${position}`;
  return (
    <div className="grid items-end gap-3 sm:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))_auto]">
      <Field label={name}>
        <ParamSelect
          label={name}
          value={axis.key}
          params={params}
          used={used}
          onChange={(key) => {
            const picked = params.find((item) => item.key === key);
            if (picked) onChange(defaultAxis(picked));
          }}
        />
      </Field>
      <Field label="From">
        <NumberInput label={`${name}: from`} value={axis.from} onChange={set("from")} step={String(param?.spec.step ?? "any")} />
      </Field>
      <Field label="To">
        <NumberInput label={`${name}: to`} value={axis.to} onChange={set("to")} step={String(param?.spec.step ?? "any")} />
      </Field>
      <Field label="Step">
        <NumberInput label={`${name}: step`} value={axis.step} onChange={set("step")} step={String(param?.spec.step ?? "any")} min={0} />
      </Field>
      <Button variant="ghost" onClick={onRemove} aria-label={`Remove parameter ${position}`}>
        Remove
      </Button>
      <p className={`text-xs sm:col-span-5 ${range?.values ? "text-muted" : "text-down"}`}>
        {!param
          ? "This parameter is not part of the setup: choose another."
          : range?.values
            ? `${plural(range.values.length, "value")}: ${range.values.slice(0, 6).map(formatValue).join(", ")}${range.values.length > 6 ? ", …" : ""} (setup: ${formatValue(param.current)})`
            : range?.problem}
      </p>
    </div>
  );
}

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
  const [draft, setDraft] = useState(initial);
  useEffect(() => setDraft(initial), [initial]);
  const limits = config.sweep;
  const params = useMemo(() => sweepParams(draft, config, signals), [draft, config, signals]);
  const used = draft.axes.map((axis) => axis.key);
  const ranges = draft.axes.map((axis) => {
    const param = params.find((item) => item.key === axis.key);
    return param ? axisValues(axis, param.spec, limits) : { values: null, problem: "unknown parameter" };
  });
  const count = combinations(ranges);
  const changes = setupChanges(draft, config);
  const invalid = hasSetupProblems(draft, config, signals) || sweepBody(draft, params, limits) === null;

  const setAxis = (index: number, axis: AxisForm) => setDraft({ ...draft, axes: draft.axes.map((item, at) => (at === index ? axis : item)) });
  const addAxis = () => {
    const next = params.find((param) => !used.includes(param.key));
    if (next) setDraft({ ...draft, axes: [...draft.axes, defaultAxis(next)] });
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!invalid) onSubmit(draft);
  };

  return (
    <Panel>
      <form onSubmit={submit} noValidate className="space-y-4">
        <BacktestSetupFields draft={draft} onChange={setDraft} config={config} signals={signals} />
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Swept parameters</h2>
          <p className="text-xs text-muted">
            One or two parameters of the setup above. Ranges start around the setup's value, in the parameter's own steps and limits.
          </p>
          {draft.axes.map((axis, index) => (
            <AxisFields
              key={index}
              position={index + 1}
              axis={axis}
              params={params}
              used={used}
              limits={limits}
              onChange={(next) => setAxis(index, next)}
              onRemove={() => setDraft({ ...draft, axes: draft.axes.filter((_, at) => at !== index) })}
            />
          ))}
          {draft.axes.length < limits.max_axes && (
            <Button onClick={addAxis} disabled={!draft.signal || used.length >= params.length}>
              {draft.axes.length ? "Add a second parameter" : "Add a parameter"}
            </Button>
          )}
        </section>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className={`num text-sm ${count !== null && count > limits.max_combinations ? "text-down" : "text-muted"}`}>
            {count === null
              ? draft.axes.length
                ? "Fix the ranges above."
                : "Pick a parameter to sweep."
              : `${ranges.length > 1 ? `${ranges.map((range) => range.values?.length).join(" × ")} = ` : ""}${plural(count, "combination")} (at most ${limits.max_combinations})`}
          </p>
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

function sameValues(left: number[], right: number[]): boolean {
  return left.length === right.length && left.every((value, index) => Math.abs(value - (right[index] ?? NaN)) <= 1e-9 * Math.max(1, Math.abs(value)));
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
  const { axes, cells } = result;
  const counts = axes.map((axis) => axis.values.length);
  const scale = useMemo(() => heatScale(cells, metric), [cells, metric]);
  const best = useMemo(() => bestCell(cells, metric), [cells, metric]);
  const current = useMemo(() => {
    const index = cells.findIndex((cell) => sameValues(cell.values, axes.map((axis) => axis.current)));
    return index < 0 ? null : index;
  }, [cells, axes]);
  const [selected, setSelected] = useState<number | null>(best);
  useEffect(() => setSelected(best), [result]); // a new sweep starts on its best cell, a new metric keeps the pick

  const metricLabel = METRICS.find((item) => item.key === metric)?.label ?? metric;
  const errors = cells.filter((cell) => cell.error);
  const value = (index: number | null, period: Period) => (index === null ? DASH : cellText(cells[index]!, period, metric));
  const medianText = (period: Period) => {
    const middle = median(periodValues(cells, period, metric));
    return middle === null ? DASH : fmtNumber(middle);
  };
  const share = aboveBreakEven(cells, "out_of_sample", metric);
  const axisParams = axes.map((axis) => params.find((param) => param.key === axis.key));
  const cell = selected === null ? undefined : cells[selected];

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
          {plural(cells.length, "combination")} on the {result.engine} engine · {describeSplit(result.split)}
        </p>
        <p className="text-xs text-muted">{PERIOD_NOTE}</p>
      </div>
      {errors.length > 0 && (
        <Notice>
          {plural(errors.length, "combination")} could not run, e.g. {errors[0]!.error}
        </Notice>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Colour by">
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
        <StatTile label={`Best in-sample ${metricLabel}`} value={value(best, "in_sample")} sub={best === null ? undefined : describeCombination(axes, cells[best]!.values)} />
        <StatTile label="Same setting out-of-sample" value={value(best, "out_of_sample")} sub={best === null ? undefined : `${cells[best]!.out_of_sample?.trades ?? 0} trades`} />
        <StatTile label={`Median ${metricLabel}`} value={`${medianText("in_sample")} → ${medianText("out_of_sample")}`} sub="in-sample → out-of-sample" />
        <StatTile
          label="Above break-even out-of-sample"
          value={share === null ? DASH : fmtPct(share * 100, 0)}
          sub={share === null ? `${metricLabel} has no break-even` : "of the combinations"}
        />
      </div>
      <Panel className="space-y-4">
        <div className="grid gap-4 xl:grid-cols-2">
          {(["in_sample", "out_of_sample"] as const).map((period) => (
            <SweepHeatmap
              key={period}
              title={
                period === "in_sample"
                  ? `In-sample ${result.split.in_sample_start} → ${result.split.in_sample_end}`
                  : `Out-of-sample (last ${result.split.oos_pct}%) ${result.split.out_of_sample_start} → ${result.split.out_of_sample_end}`
              }
              period={period}
              axes={axes}
              cells={cells}
              metric={metric}
              scale={scale}
              selected={selected}
              best={best}
              current={current}
              onSelect={setSelected}
            />
          ))}
        </div>
        <SweepLegend scale={scale} metric={metric} />
      </Panel>
      {cell && selected !== null && (
        <section className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">{describeCombination(axes, cell.values)}</h2>
            {axisParams.every(Boolean) && (
              <Link
                to={`/backtest?${writeBacktestForm({ ...withCombination(form, axisParams as SweepParam[], cell.values), engines: [result.engine] }, config).toString()}`}
                className="text-sm text-accent hover:underline"
              >
                Open in Backtest →
              </Link>
            )}
          </div>
          {cell.error ? (
            <Notice>This combination could not run: {cell.error}</Notice>
          ) : (
            <>
              <p className="text-xs text-muted">
                Neighbouring settings average {metricLabel}{" "}
                {(["in_sample", "out_of_sample"] as const)
                  .map((period) => {
                    const average = neighbourAverage(cells, selected, counts, period, metric);
                    const own = cellValue(cell, period, metric);
                    return `${period === "in_sample" ? "in-sample" : "out-of-sample"} ${average === null ? DASH : fmtNumber(average)} (this cell ${own === null ? DASH : fmtNumber(own)})`;
                  })
                  .join(", ")}
                . A result that only one cell reaches is likely luck.
              </p>
              <MetricsTable
                caption="Metrics of the selected combination in both periods"
                columns={[
                  { key: "in", header: "In-sample", metrics: cell.in_sample },
                  { key: "out", header: "Out-of-sample", metrics: cell.out_of_sample },
                ]}
              />
              {(["in_sample", "out_of_sample"] as const).map((period) => {
                const trades = cell[period]?.trades ?? 0;
                return trades < MIN_TRADES ? (
                  <p key={period} className="text-xs text-warn">
                    {period === "in_sample" ? "In-sample" : "Out-of-sample"}: only {trades} trades, too few to trust the metrics.
                  </p>
                ) : null;
              })}
            </>
          )}
        </section>
      )}
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
  const sweepable = useMemo(() => (form && config.data && signals.data ? sweepParams(form, config.data, signals.data) : []), [form, config.data, signals.data]);
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
      {sweep.isError && <ErrorBox error={sweep.error} onRetry={() => sweep.refetch()} />}
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
