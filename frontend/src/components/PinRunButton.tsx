import { useMemo } from "react";
import { Link } from "react-router";

import type { BacktestOut, PortfolioOut } from "../api/client";
import type { BacktestForm } from "../lib/params";
import type { PortfolioForm } from "../lib/portfolio";
import { MAX_RUNS, runKey, snapshotPortfolioRun, snapshotRun, type RunSnapshot } from "../lib/runs";
import { usePinnedRuns } from "../state/pinnedRuns";
import { Button } from "./ui";

/** Pins a run for the Compare page, or unpins it when it is already pinned; `what` names the run on the button. */
function PinSnapshotButton({ snapshot, what }: { snapshot: RunSnapshot | null; what: string }) {
  const { runs, pin, remove } = usePinnedRuns();
  const pinned = useMemo(() => {
    if (!snapshot) return undefined;
    const key = runKey(snapshot);
    return runs.find((run) => runKey(run) === key);
  }, [runs, snapshot]);
  if (!snapshot) return null;

  const full = !pinned && runs.length >= MAX_RUNS;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {runs.length > 0 && (
        <Link to="/compare" className="text-sm text-accent hover:underline">
          Compare {runs.length} pinned →
        </Link>
      )}
      {full && <span className="text-xs text-muted">{MAX_RUNS} runs pinned: remove one to pin more</span>}
      {pinned ? (
        <Button onClick={() => remove(pinned.id)}>Unpin {what}</Button>
      ) : (
        <Button variant="primary" onClick={() => pin(snapshot)} disabled={full}>
          Pin {what}
        </Button>
      )}
    </div>
  );
}

const runName = (engines: number, engine: string) => (engines > 1 ? `${engine} run` : "run");

/** Pins the shown engine's backtest run. */
export function PinRunButton({ result, engine, form }: { result: BacktestOut; engine: string; form: BacktestForm }) {
  const snapshot = useMemo(() => snapshotRun(result, engine, form), [result, engine, form]);
  return <PinSnapshotButton snapshot={snapshot} what={runName(result.runs.length, engine)} />;
}

/** Pins the shown engine's portfolio run. */
export function PinPortfolioRunButton({ result, engine, form }: { result: PortfolioOut; engine: string; form: PortfolioForm }) {
  const snapshot = useMemo(() => snapshotPortfolioRun(result, engine, form), [result, engine, form]);
  return <PinSnapshotButton snapshot={snapshot} what={runName(result.runs.length, engine)} />;
}
