import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { serverRunStore, type RunPatch, type RunStore } from "../lib/runStore";
import { MAX_RUNS, mergeRuns, sortBySlot, toPinnedRun, type MergeResult, type PinnedRun, type RunSnapshot } from "../lib/runs";
import { decodeRuns, encodeRuns, parseRunsFile } from "../lib/runsFile";

/** Where versions before server-side runs kept the pinned runs, in this browser only. */
const BROWSER_KEY = "tradescan.runs";

interface PinnedRunsValue {
  /** Ordered by slot. */
  runs: PinnedRun[];
  /** True until the runs are first read from the server. */
  loading: boolean;
  /** Why the runs could not be read or the last change could not be saved. */
  error: string | null;
  /** What happened to the runs found in this browser's storage. */
  notice: string | null;
  pin: (snapshot: RunSnapshot) => void;
  remove: (id: string) => void;
  update: (id: string, patch: RunPatch) => void;
  clear: () => void;
  /** Merges the runs of an exported file; throws when the file is invalid or the server did not keep them. */
  importRuns: (content: string) => Promise<MergeResult>;
  exportRuns: () => string;
}

const PinnedRunsContext = createContext<PinnedRunsValue | null>(null);

const reason = (problem: unknown) => (problem instanceof Error ? problem.message : String(problem));

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** The runs a merge added: the ones that were not there before. */
const addedRuns = (before: PinnedRun[], result: MergeResult) => result.runs.filter((run) => !before.includes(run));

async function addAll(store: RunStore, runs: PinnedRun[]): Promise<void> {
  for (const run of runs) await store.add(run);
}

interface Moved {
  runs: PinnedRun[];
  notice: string | null;
  error: string | null;
}

/**
 * Move the runs this browser still keeps to the server. The browser's copy is deleted only once every run is on
 * the server, so runs that did not fit or could not be saved are tried again on the next load.
 */
async function moveBrowserRuns(store: RunStore, current: PinnedRun[]): Promise<Moved> {
  let raw: string | null;
  try {
    raw = localStorage.getItem(BROWSER_KEY);
  } catch {
    return { runs: current, notice: null, error: null };
  }
  if (raw === null) return { runs: current, notice: null, error: null };
  let saved: PinnedRun[];
  try {
    saved = decodeRuns(JSON.parse(raw));
  } catch (problem) {
    return { runs: current, notice: null, error: `Pinned runs saved in this browser could not be read (${reason(problem)}).` };
  }
  const result = mergeRuns(current, saved);
  const added = addedRuns(current, result);
  try {
    await addAll(store, added);
  } catch (problem) {
    return { runs: await store.load(), notice: null, error: `Pinned runs saved in this browser could not be moved to the server (${reason(problem)}).` };
  }
  if (!added.length && !result.overflow) {
    // Every run is on the server already: an earlier move could not delete the browser's copy.
    removeBrowserRuns();
    return { runs: current, notice: null, error: null };
  }
  const parts = [`Moved ${plural(added.length, "pinned run")} from this browser to the server.`];
  if (result.duplicates) parts.push(`${plural(result.duplicates, "run")} already there.`);
  if (result.overflow) {
    parts.push(`${plural(result.overflow, "run")} did not fit (the limit is ${MAX_RUNS}): remove some runs and reload the page to move the rest.`);
  } else {
    removeBrowserRuns();
  }
  return { runs: result.runs, notice: parts.join(" "), error: null };
}

function removeBrowserRuns(): void {
  try {
    localStorage.removeItem(BROWSER_KEY);
  } catch {
    // Blocked storage: the runs are tried again next time and are then duplicates.
  }
}

export function PinnedRunsProvider({ children, store = serverRunStore }: { children: ReactNode; store?: RunStore }) {
  const [runs, setRuns] = useState<PinnedRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let loaded: PinnedRun[];
      try {
        loaded = await store.load();
      } catch (problem) {
        if (!cancelled) setError(`Pinned runs could not be read from the server (${reason(problem)}).`);
        return;
      }
      if (cancelled) return;
      const moved = await moveBrowserRuns(store, loaded);
      if (cancelled) return;
      setRuns(moved.runs);
      setNotice(moved.notice);
      setError(moved.error);
    })()
      .catch((problem: unknown) => {
        if (!cancelled) setError(`Pinned runs could not be read from the server (${reason(problem)}).`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [store]);

  /** Show what the server has; keeps the last error, since a reload follows a failed change. */
  const refresh = useCallback(async () => {
    try {
      setRuns(await store.load());
    } catch (problem) {
      setError(`Pinned runs could not be read from the server (${reason(problem)}).`);
    }
  }, [store]);

  // Another tab or browser may have pinned or removed runs meanwhile.
  useEffect(() => {
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  /** Show `next` at once and save it with `write`; false, with the reason shown, when the server refused. */
  const save = useCallback(
    async (next: PinnedRun[], write: () => Promise<void>): Promise<boolean> => {
      setRuns(next);
      try {
        await write();
        setError(null);
        return true;
      } catch (problem) {
        setError(`The change was not saved (${reason(problem)}).`);
        await refresh();
        return false;
      }
    },
    [refresh],
  );

  const value = useMemo<PinnedRunsValue>(
    () => ({
      runs,
      loading,
      error,
      notice,
      pin: (snapshot) => {
        const result = mergeRuns(runs, [toPinnedRun(snapshot)]);
        if (result.added) void save(result.runs, () => addAll(store, addedRuns(runs, result)));
      },
      remove: (id) => void save(runs.filter((run) => run.id !== id), () => store.remove(id)),
      update: (id, patch) => void save(sortBySlot(runs.map((run) => (run.id === id ? { ...run, ...patch } : run))), () => store.update(id, patch)),
      clear: () => void save([], () => store.clear()),
      importRuns: async (content) => {
        const result = mergeRuns(runs, parseRunsFile(content));
        if (result.added && !(await save(result.runs, () => addAll(store, addedRuns(runs, result))))) {
          throw new Error("the server did not keep the runs");
        }
        return result;
      },
      exportRuns: () => JSON.stringify(encodeRuns(runs)),
    }),
    [runs, loading, error, notice, store, save],
  );

  return <PinnedRunsContext.Provider value={value}>{children}</PinnedRunsContext.Provider>;
}

export function usePinnedRuns(): PinnedRunsValue {
  const value = useContext(PinnedRunsContext);
  if (!value) throw new Error("usePinnedRuns must be used inside PinnedRunsProvider");
  return value;
}
