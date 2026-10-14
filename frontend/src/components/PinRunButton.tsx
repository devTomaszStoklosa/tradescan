import { useMemo } from "react";
import { Link } from "react-router";

import type { BacktestOut } from "../api/client";
import type { BacktestForm } from "../lib/params";
import { MAX_RUNS, runKey, snapshotRun } from "../lib/runs";
import { usePinnedRuns } from "../state/pinnedRuns";
import { Button } from "./ui";

/** Pins the shown engine's run for the Compare page, or unpins it when it is already pinned. */
export function PinRunButton({ result, engine, form }: { result: BacktestOut; engine: string; form: BacktestForm }) {
  const { runs, pin, remove } = usePinnedRuns();
  const snapshot = useMemo(() => snapshotRun(result, engine, form), [result, engine, form]);
  const pinned = useMemo(() => {
    if (!snapshot) return undefined;
    const key = runKey(snapshot);
    return runs.find((run) => runKey(run) === key);
  }, [runs, snapshot]);
  if (!snapshot) return null;

  const full = !pinned && runs.length >= MAX_RUNS;
  const what = result.runs.length > 1 ? `${engine} run` : "run";
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
