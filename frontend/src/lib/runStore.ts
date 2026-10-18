/**
 * Where pinned runs are kept: on the tradescan server, so every browser sees the same runs. Tests give the
 * provider a store of their own.
 */
import { api } from "../api/client";
import type { PinnedRun } from "./runs";
import { decodeRunRecord, runRecord } from "./runsFile";

export type RunPatch = Partial<Pick<PinnedRun, "name" | "hidden">>;

export interface RunStore {
  /** Every run, by slot; throws when they cannot be read. */
  load: () => Promise<PinnedRun[]>;
  /** Throws when the run's id is already kept or another run holds its slot. */
  add: (run: PinnedRun) => Promise<void>;
  update: (id: string, patch: RunPatch) => Promise<void>;
  remove: (id: string) => Promise<void>;
  clear: () => Promise<void>;
}

export const serverRunStore: RunStore = {
  load: async () => (await api.runs()).map((record, index) => decodeRunRecord(record, index)),
  add: async (run) => {
    await api.pinRun(runRecord(run));
  },
  update: async (id, patch) => {
    await api.updateRun(id, patch);
  },
  remove: (id) => api.unpinRun(id),
  clear: () => api.clearRuns(),
};
