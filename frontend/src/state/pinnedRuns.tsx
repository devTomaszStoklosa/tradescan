import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { mergeRuns, sortBySlot, toPinnedRun, type MergeResult, type PinnedRun, type RunSnapshot } from "../lib/runs";
import { decodeRuns, encodeRuns, parseRunsFile } from "../lib/runsFile";
import { writeStorage } from "../lib/storage";

const STORAGE_KEY = "tradescan.runs";

type RunPatch = Partial<Pick<PinnedRun, "name" | "hidden">>;

interface PinnedRunsValue {
  /** Ordered by slot. */
  runs: PinnedRun[];
  /** Why saved runs could not be read or the last change could not be saved. */
  error: string | null;
  pin: (snapshot: RunSnapshot) => void;
  remove: (id: string) => void;
  update: (id: string, patch: RunPatch) => void;
  clear: () => void;
  /** Merges the runs of an exported file; throws when the file is invalid. */
  importRuns: (content: string) => MergeResult;
  exportRuns: () => string;
}

const PinnedRunsContext = createContext<PinnedRunsValue | null>(null);

interface Loaded {
  runs: PinnedRun[];
  error: string | null;
}

function load(raw: string | null): Loaded {
  if (raw === null) return { runs: [], error: null };
  try {
    return { runs: mergeRuns([], decodeRuns(JSON.parse(raw))).runs, error: null };
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return { runs: [], error: `Pinned runs saved in this browser could not be read (${reason}).` };
  }
}

function readSaved(): Loaded {
  try {
    return load(localStorage.getItem(STORAGE_KEY));
  } catch {
    return { runs: [], error: "Browser storage is blocked, so pinned runs are kept only until the page closes." };
  }
}

const SAVE_FAILED = "Browser storage is full or blocked, so this change was not saved. Export the runs or remove some.";

export function PinnedRunsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Loaded>(readSaved);
  const { runs } = state;

  const commit = useCallback((next: PinnedRun[]) => {
    const saved = writeStorage(STORAGE_KEY, encodeRuns(next));
    setState({ runs: next, error: saved ? null : SAVE_FAILED });
  }, []);

  // Another tab pinned or removed a run: show the same runs here.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) setState(load(event.newValue));
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const value = useMemo<PinnedRunsValue>(
    () => ({
      runs,
      error: state.error,
      pin: (snapshot) => {
        const result = mergeRuns(runs, [toPinnedRun(snapshot)]);
        if (result.added) commit(result.runs);
      },
      remove: (id) => commit(runs.filter((run) => run.id !== id)),
      update: (id, patch) => commit(sortBySlot(runs.map((run) => (run.id === id ? { ...run, ...patch } : run)))),
      clear: () => commit([]),
      importRuns: (content) => {
        const result = mergeRuns(runs, parseRunsFile(content));
        if (result.added) commit(result.runs);
        return result;
      },
      exportRuns: () => JSON.stringify(encodeRuns(runs)),
    }),
    [runs, state.error, commit],
  );

  return <PinnedRunsContext.Provider value={value}>{children}</PinnedRunsContext.Provider>;
}

export function usePinnedRuns(): PinnedRunsValue {
  const value = useContext(PinnedRunsContext);
  if (!value) throw new Error("usePinnedRuns must be used inside PinnedRunsProvider");
  return value;
}
