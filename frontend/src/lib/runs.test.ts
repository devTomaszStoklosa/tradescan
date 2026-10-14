import { describe, expect, it } from "vitest";

import { backtestForm, backtestResult, makeRun } from "../test/fixtures";
import { freeSlot, MAX_RUNS, mergeRuns, runKey, snapshotRun, toPinnedRun } from "./runs";
import { decodeRuns, encodeRuns, parseRunsFile, RUNS_FILE_VERSION } from "./runsFile";

describe("snapshotRun", () => {
  it("keeps one engine's result and reopens with only that engine", () => {
    const snapshot = snapshotRun(backtestResult, "vectorized", { ...backtestForm, engines: ["vectorized", "cerebro"] });
    expect(snapshot).toMatchObject({ ticker: "SPY", engine: "vectorized", start: "2016-01-04", end: "2026-10-13" });
    expect(snapshot?.form.engines).toEqual(["vectorized"]);
    expect(snapshot?.metrics.trades).toBe(42);
    expect(snapshot).not.toHaveProperty("trades");
  });

  it("returns null for an engine that did not run", () => {
    expect(snapshotRun(backtestResult, "cerebro", backtestForm)).toBeNull();
  });
});

describe("runKey", () => {
  it("ignores names, slots and key order but not parameters or the data range", () => {
    const run = makeRun(1);
    expect(runKey(makeRun(2, {}, { name: "other" }))).toBe(runKey(run));
    expect(runKey(makeRun(1, { params: { oversold: 10, trend_period: 200, rsi_period: 2 } }))).toBe(runKey(run));
    expect(runKey(makeRun(1, { params: { ...run.params, oversold: 15 } }))).not.toBe(runKey(run));
    expect(runKey(makeRun(1, { config: { ...run.config, atr_mult: 3 } }))).not.toBe(runKey(run));
    expect(runKey(makeRun(1, { end: "2026-10-14" }))).not.toBe(runKey(run));
  });
});

describe("mergeRuns", () => {
  it("assigns the lowest free slot and skips runs already pinned", () => {
    const first = makeRun(1);
    const result = mergeRuns([first], [toPinnedRun(makeRun(1, { config: { ...first.config, atr_mult: 3 } })), toPinnedRun(first)]);
    expect(result.runs.map((run) => run.slot)).toEqual([1, 2]);
    expect(result).toMatchObject({ added: 1, duplicates: 1, overflow: 0 });
  });

  it("keeps a free slot, re-slots a taken one and replaces a taken id", () => {
    const current = [makeRun(3)];
    const incoming = [makeRun(5, { end: "2026-01-02" }), makeRun(3, { end: "2026-01-05" }, { id: "run-3" })];
    const { runs } = mergeRuns(current, incoming);
    expect(runs.map((run) => run.slot)).toEqual([1, 3, 5]);
    expect(new Set(runs.map((run) => run.id)).size).toBe(3);
  });

  it(`stops at ${MAX_RUNS} runs`, () => {
    const incoming = Array.from({ length: MAX_RUNS + 2 }, (_, index) => makeRun(1, { end: `2026-01-${String(index + 1).padStart(2, "0")}` }));
    const result = mergeRuns([], incoming);
    expect(result.runs).toHaveLength(MAX_RUNS);
    expect(result.overflow).toBe(2);
    expect(freeSlot(result.runs)).toBeNull();
  });
});

describe("runs file", () => {
  it("round-trips runs with equity rounded to cents", () => {
    const run = makeRun(2, {}, { name: "stop 3 ATR", hidden: true });
    const file = encodeRuns([run]);
    expect(file.version).toBe(RUNS_FILE_VERSION);
    expect(file.runs[0]?.equity.value).toEqual([100000, 105000.12, 112500]);
    const [decoded] = parseRunsFile(JSON.stringify(file));
    expect(decoded).toEqual({ ...run, equity: run.equity.map((point) => ({ ...point, value: Math.round(point.value * 100) / 100 })) });
  });

  it("drops fields it does not know", () => {
    const file = encodeRuns([makeRun(1)]);
    const [decoded] = decodeRuns({ ...file, runs: [{ ...file.runs[0], extra: "x" }] });
    expect(decoded).not.toHaveProperty("extra");
  });

  it.each([
    ["not JSON", "{", "The file is not valid JSON"],
    ["another file", JSON.stringify({ hello: 1 }), "This is not a tradescan runs file"],
    ["a newer version", JSON.stringify({ version: 99, runs: [] }), "Unsupported runs file version: 99"],
    ["a run without metrics", JSON.stringify({ version: 1, runs: [{ ...encodeRuns([makeRun(1)]).runs[0], metrics: null }] }), 'Run 1 has an invalid "metrics"'],
    ["a slot out of range", JSON.stringify({ version: 1, runs: [{ ...encodeRuns([makeRun(1)]).runs[0], slot: 9 }] }), 'Run 1 has an invalid "slot"'],
    [
      "uneven equity arrays",
      JSON.stringify({ version: 1, runs: [{ ...encodeRuns([makeRun(1)]).runs[0], equity: { time: ["2020-01-01"], value: [] } }] }),
      'Run 1 has an invalid "equity"',
    ],
    [
      "a bad form value",
      JSON.stringify({ version: 1, runs: [{ ...encodeRuns([makeRun(1)]).runs[0], form: { ...backtestForm, settings: { risk: { atr_mult: "3" } } } }] }),
      'Run 1 has an invalid "form"',
    ],
  ])("rejects %s", (_, content, message) => {
    expect(() => parseRunsFile(content)).toThrow(message);
  });
});
