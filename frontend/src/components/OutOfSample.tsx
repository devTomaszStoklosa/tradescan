/** In-sample vs out-of-sample results: for one backtest run, and for pinned runs side by side. */
import type { EngineRunOut, MetricsOut, SplitOut } from "../api/client";
import { MIN_TRADES, type MetricKey } from "../lib/compare";
import { DASH } from "../lib/format";
import type { PinnedRun } from "../lib/runs";
import { METRICS, MetricsTable } from "./BacktestResults";
import { RunLabel } from "./RunCard";
import { Notice } from "./ui";

export const PERIOD_NOTE = "Each period starts with fresh equity; out-of-sample signals only fire from the split on.";

/** "In-sample 2016-01-04 → 2023-06-30 · out-of-sample (last 30%) 2023-07-03 → 2026-10-13" */
export function describeSplit(split: SplitOut): string {
  return (
    `In-sample ${split.in_sample_start} → ${split.in_sample_end} · ` +
    `out-of-sample (last ${split.oos_pct}%) ${split.out_of_sample_start} → ${split.out_of_sample_end}`
  );
}

function PeriodHeader({ title, range }: { title: string; range: string }) {
  return (
    <span className="flex flex-col items-end">
      <span>{title}</span>
      <span className="num font-normal">{range}</span>
    </span>
  );
}

/** The full history next to its two periods, for one engine's run. */
export function PeriodsPanel({
  run,
  split,
  start,
  end,
}: {
  run: EngineRunOut;
  split: SplitOut | null;
  start: string;
  end: string;
}) {
  if (!split || !run.in_sample || !run.out_of_sample) {
    return (
      <Notice>
        The history is too short to split into an in-sample and an out-of-sample period. Choose a longer history.
      </Notice>
    );
  }
  const periods: [string, MetricsOut][] = [
    ["In-sample", run.in_sample],
    ["Out-of-sample", run.out_of_sample],
  ];
  const few = periods.filter(([, metrics]) => metrics.trades < MIN_TRADES);
  const columns = [
    { key: "full", header: <PeriodHeader title="Full history" range={`${start} → ${end}`} />, metrics: run.metrics },
    {
      key: "in",
      header: <PeriodHeader title="In-sample" range={`${split.in_sample_start} → ${split.in_sample_end}`} />,
      metrics: run.in_sample,
    },
    {
      key: "out",
      header: (
        <PeriodHeader
          title={`Out-of-sample (${split.oos_pct}%)`}
          range={`${split.out_of_sample_start} → ${split.out_of_sample_end}`}
        />
      ),
      metrics: run.out_of_sample,
    },
  ];
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold">In-sample vs out-of-sample ({run.engine})</h2>
      <p className="text-xs text-muted">
        The out-of-sample period is the last part of the history: tune on the in-sample one and check here that the
        result holds. {PERIOD_NOTE}
      </p>
      <MetricsTable
        columns={columns}
        caption="Metrics of the full history and of the in-sample and out-of-sample periods"
      />
      {few.map(([title, metrics]) => (
        <p key={title} className="text-xs text-warn">
          {title}: only {metrics.trades} trades, too few to trust the metrics.
        </p>
      ))}
    </section>
  );
}

const CHECKED: MetricKey[] = ["sharpe", "expectancy_r", "profit_factor", "trades"];

function PeriodValue({ metrics, metricKey }: { metrics: MetricsOut; metricKey: MetricKey }) {
  const metric = METRICS.find((item) => item.key === metricKey);
  const few = metrics.trades < MIN_TRADES;
  return (
    <td className={`num px-3 py-1.5 text-right whitespace-nowrap ${few ? "text-warn" : ""}`}>
      {metric ? metric.format(metrics) : DASH}
      {few && (
        <>
          <span aria-hidden>*</span>
          <span className="sr-only"> (fewer than {MIN_TRADES} trades)</span>
        </>
      )}
    </td>
  );
}

/** One row per pinned run: key metrics in-sample next to out-of-sample. */
export function OutOfSampleTable({ runs }: { runs: PinnedRun[] }) {
  const labels = CHECKED.map((key) => METRICS.find((metric) => metric.key === key)?.label ?? key);
  return (
    <div className="space-y-1">
      <div className="relative overflow-x-auto rounded-xl border border-line bg-panel">
        <table className="w-full text-sm">
          <caption className="sr-only">Out-of-sample check of the pinned runs</caption>
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th scope="col" rowSpan={2} className="sticky left-0 bg-panel px-3 py-2 text-left font-medium">
                Run
              </th>
              <th scope="col" rowSpan={2} className="px-3 py-2 text-left font-medium">
                Out-of-sample from
              </th>
              {labels.map((label) => (
                <th
                  key={label}
                  scope="colgroup"
                  colSpan={2}
                  className="border-l border-line px-3 pt-2 text-center font-medium"
                >
                  {label}
                </th>
              ))}
            </tr>
            <tr className="border-b border-line text-xs text-muted">
              {CHECKED.flatMap((key) => [
                <th key={`${key}-in`} scope="col" className="border-l border-line px-3 pb-2 text-right font-normal">
                  in
                </th>,
                <th key={`${key}-out`} scope="col" className="px-3 pb-2 text-right font-normal">
                  out
                </th>,
              ])}
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-b border-line last:border-0">
                <th scope="row" className="sticky left-0 bg-panel px-3 py-1.5 text-left font-normal">
                  <RunLabel run={run} />
                </th>
                {run.split ? (
                  <>
                    <td className="num px-3 py-1.5 whitespace-nowrap text-muted">
                      {run.split.out_of_sample_start} ({run.split.oos_pct}%)
                    </td>
                    {CHECKED.flatMap((key) => [
                      <PeriodValue key={`${key}-in`} metrics={run.split!.in_sample} metricKey={key} />,
                      <PeriodValue key={`${key}-out`} metrics={run.split!.out_of_sample} metricKey={key} />,
                    ])}
                  </>
                ) : (
                  <td colSpan={1 + CHECKED.length * 2} className="px-3 py-1.5 text-muted">
                    No split: pinned before out-of-sample results or with too short a history.
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        * fewer than {MIN_TRADES} trades. {PERIOD_NOTE}
      </p>
    </div>
  );
}
