import { useMemo, useRef, useState, type ChangeEvent } from "react";
import { Link } from "react-router";

import { useConfig, useSignals } from "../api/hooks";
import { MetricsTable } from "../components/BacktestResults";
import { EquityChart, type EquitySeries } from "../components/charts/EquityChart";
import { MonteCarloTable } from "../components/MonteCarlo";
import { OutOfSampleTable } from "../components/OutOfSample";
import { ParameterDiffTable } from "../components/ParameterDiffTable";
import { PortfolioStatsTable } from "../components/PortfolioStats";
import { RunCard, RunLabel } from "../components/RunCard";
import { Button, EmptyState, ErrorBox, PageHeader, Panel, Segmented } from "../components/ui";
import { parameterRows, returnCurve } from "../lib/compare";
import { downloadFile } from "../lib/csv";
import { methodsOf, PREFERRED_METHOD } from "../lib/monteCarlo";
import { asPortfolio, MAX_RUNS, runColorVar, type MergeResult, type PinnedRun } from "../lib/runs";
import { usePinnedRuns } from "../state/pinnedRuns";

type Period = "full" | "in_sample" | "out_of_sample";

const PERIODS: { value: Period; label: string }[] = [
  { value: "full", label: "Full history" },
  { value: "in_sample", label: "In-sample" },
  { value: "out_of_sample", label: "Out-of-sample" },
];

const periodMetrics = (run: PinnedRun, period: Period) => (period === "full" ? run.metrics : (run.split?.[period] ?? null));

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

function describeImport({ added, duplicates, overflow }: MergeResult): string {
  const parts = [`Imported ${plural(added, "run")}.`];
  if (duplicates) parts.push(`${plural(duplicates, "run")} already pinned.`);
  if (overflow) parts.push(`${plural(overflow, "run")} did not fit: the limit is ${MAX_RUNS}.`);
  return parts.join(" ");
}

export function ComparePage() {
  const { runs, error, update, remove, clear, importRuns, exportRuns } = usePinnedRuns();
  // Labels and units only; without the server the page still works with the stored runs.
  const config = useConfig();
  const signals = useSignals();
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [period, setPeriod] = useState<Period>("full");
  const [chosenMethod, setMethod] = useState(PREFERRED_METHOD);

  const visible = useMemo(() => runs.filter((run) => !run.hidden), [runs]);
  const rows = useMemo(() => parameterRows(visible, config.data?.sections, signals.data, config.data), [visible, config.data, signals.data]);
  const columns = useMemo(
    () => visible.map((run) => ({ key: run.id, header: <RunLabel run={run} />, metrics: periodMetrics(run, period) })),
    [visible, period],
  );
  const statColumns = useMemo(
    () =>
      visible.flatMap((item) => {
        const run = asPortfolio(item);
        return run ? [{ key: run.id, header: <RunLabel run={run} />, stats: run.stats[period] }] : [];
      }),
    [visible, period],
  );
  const methods = useMemo(() => methodsOf(visible.map((run) => run.monteCarlo)), [visible]);
  const method = methods.some((item) => item.name === chosenMethod) ? chosenMethod : (methods[0]?.name ?? chosenMethod);
  const series = useMemo<EquitySeries[]>(
    () => visible.map((run) => ({ label: `#${run.slot} ${run.name}`, points: returnCurve(run.equity), colorVar: runColorVar(run) })),
    [visible],
  );

  const onImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      setMessage({ ok: true, text: describeImport(importRuns(await file.text())) });
    } catch (problem) {
      setMessage({ ok: false, text: `Import failed: ${problem instanceof Error ? problem.message : String(problem)}` });
    }
  };

  const onExport = () => downloadFile(`tradescan-runs-${new Date().toISOString().slice(0, 10)}.json`, exportRuns(), "application/json");

  const onClear = () => {
    if (window.confirm(`Remove all ${plural(runs.length, "pinned run")}? Export them first if you want a backup.`)) clear();
  };

  return (
    <>
      <PageHeader
        title="Compare"
        subtitle={`Pinned backtest and portfolio runs side by side, up to ${MAX_RUNS}. They are kept in this browser only: export them as a backup.`}
        actions={
          <>
            <input ref={fileInput} type="file" accept="application/json,.json" aria-label="Runs file to import" className="hidden" onChange={onImport} />
            <Button onClick={() => fileInput.current?.click()}>Import JSON</Button>
            <Button onClick={onExport} disabled={!runs.length}>
              Export JSON
            </Button>
            <Button variant="ghost" onClick={onClear} disabled={!runs.length}>
              Remove all
            </Button>
          </>
        }
      />
      {error && <ErrorBox error={error} />}
      {message && (
        <p role="status" className={`text-sm ${message.ok ? "text-muted" : "text-down"}`}>
          {message.text}
        </p>
      )}
      {!runs.length ? (
        <EmptyState title="No pinned runs yet">
          Run a <Link to="/backtest" className="text-accent hover:underline">backtest</Link> or a{" "}
          <Link to="/portfolio" className="text-accent hover:underline">portfolio</Link> and press <strong>Pin run</strong> to keep it here, then change
          a parameter and pin again.
        </EmptyState>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {runs.map((run) => (
              <RunCard
                key={run.id}
                run={run}
                onRename={(name) => update(run.id, { name })}
                onToggle={() => update(run.id, { hidden: !run.hidden })}
                onRemove={() => remove(run.id)}
              />
            ))}
          </div>
          {visible.length ? (
            <>
              <Panel>
                <ParameterDiffTable runs={visible} rows={rows} />
              </Panel>
              <section className="space-y-2">
                <h2 className="text-sm font-semibold">Out-of-sample check</h2>
                <OutOfSampleTable runs={visible} />
              </section>
              <section className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-sm font-semibold">Monte Carlo of the trades</h2>
                  {methods.length > 1 && (
                    <Segmented label="Method" value={method} onChange={setMethod} options={methods.map(({ name, label }) => ({ value: name, label }))} />
                  )}
                </div>
                <MonteCarloTable runs={visible} method={method} />
              </section>
              <section className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-sm font-semibold">Metrics</h2>
                  <Segmented label="Period" value={period} onChange={setPeriod} options={PERIODS} />
                </div>
                <MetricsTable columns={columns} caption={period === "full" ? "Metrics of the pinned runs" : `Metrics of the pinned runs, ${period === "in_sample" ? "in-sample" : "out-of-sample"}`} highlightBest />
                <p className="text-xs text-muted">
                  The best value of each ranked metric is highlighted.{period !== "full" && " Runs without a split show dashes."}
                </p>
              </section>
              {statColumns.length > 0 && (
                <section className="space-y-2">
                  <h2 className="text-sm font-semibold">Portfolio stats</h2>
                  <PortfolioStatsTable
                    columns={statColumns}
                    caption={`Portfolio stats of the pinned portfolio runs${period === "full" ? "" : `, ${period === "in_sample" ? "in-sample" : "out-of-sample"}`}`}
                  />
                  <p className="text-xs text-muted">Portfolio runs only, for the period chosen under Metrics.</p>
                </section>
              )}
              <Panel>
                <h2 className="mb-2 text-sm font-semibold">Return since the first bar</h2>
                <EquityChart series={series} format="percent" label="Return of the pinned runs since their first bar" />
              </Panel>
            </>
          ) : (
            <EmptyState title="Every run is hidden">Press Show on a run to compare it.</EmptyState>
          )}
        </>
      )}
    </>
  );
}
