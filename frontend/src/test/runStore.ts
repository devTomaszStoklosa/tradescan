import type { PinnedRunIn } from "../api/client";
import type { RunPatch, RunStore } from "../lib/runStore";
import { sortBySlot, type PinnedRun } from "../lib/runs";
import { decodeRunRecord, runRecord } from "../lib/runsFile";

const asJson = (run: PinnedRun): PinnedRunIn => JSON.parse(JSON.stringify(runRecord(run))) as PinnedRunIn;

/** Pinned runs in memory, kept as the server keeps them: as JSON records, with a taken id or slot refused. */
export class MemoryRunStore implements RunStore {
  records: PinnedRunIn[];

  constructor(runs: PinnedRun[] = []) {
    this.records = runs.map(asJson);
  }

  /** The kept runs, by slot. */
  runs(): PinnedRun[] {
    return sortBySlot(this.records.map((record, index) => decodeRunRecord(record, index)));
  }

  load = async () => this.runs();

  add = async (run: PinnedRun) => {
    if (this.records.some((record) => record.id === run.id || record.slot === run.slot))
      throw new Error(`Slot ${run.slot} is taken by another pinned run`);
    this.records.push(asJson(run));
  };

  update = async (id: string, patch: RunPatch) => {
    const record = this.records.find((item) => item.id === id);
    if (!record) throw new Error(`No pinned run ${id}`);
    Object.assign(record, patch);
  };

  remove = async (id: string) => {
    if (!this.records.some((record) => record.id === id)) throw new Error(`No pinned run ${id}`);
    this.records = this.records.filter((record) => record.id !== id);
  };

  clear = async () => {
    this.records = [];
  };
}
