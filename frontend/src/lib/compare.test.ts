import { describe, expect, it } from "vitest";

import { config, makeMetrics, makeRun, signals } from "../test/fixtures";
import { bestIndexes, metricValue, parameterRows, returnCurve } from "./compare";

const differing = (rows: ReturnType<typeof parameterRows>) => rows.filter((row) => row.differs);

describe("parameterRows", () => {
  it("flags only the parameters that differ, with labels and units from the specs", () => {
    const base = makeRun(1);
    const changed = makeRun(2, { config: { ...base.config, atr_mult: 3 }, params: { ...base.params, oversold: 15 } });
    const rows = parameterRows([base, changed], config.sections, signals);

    expect(differing(rows)).toEqual([
      { key: "config.atr_mult", label: "Stop distance", unit: "ATR", values: ["2", "3"], differs: true },
      { key: "params.connors_rsi2_long.oversold", label: "connors_rsi2_long · Oversold level", unit: "", values: ["10", "15"], differs: true },
    ]);
    expect(rows.find((row) => row.key === "ticker")).toMatchObject({ values: ["SPY", "SPY"], differs: false });
  });

  it("falls back to readable names without specs", () => {
    const rows = parameterRows([makeRun(1)]);
    expect(rows.find((row) => row.key === "config.initial_equity")).toMatchObject({ label: "Initial equity", values: ["100,000"] });
    expect(rows.find((row) => row.key === "params.connors_rsi2_long.trend_period")?.label).toBe("connors_rsi2_long · Trend period");
  });

  it("keeps parameters of different signals in separate rows", () => {
    const rsi = makeRun(1);
    const donchian = makeRun(2, { signal: "donchian_breakout", params: { period: 20 } });
    const rows = parameterRows([rsi, donchian], config.sections, signals);

    expect(rows.find((row) => row.key === "params.donchian_breakout.period")).toMatchObject({ values: ["–", "20"], differs: true });
    expect(rows.find((row) => row.key === "params.connors_rsi2_long.rsi_period")).toMatchObject({ values: ["2", "–"], differs: true });
    expect(rows.find((row) => row.key === "signal")?.differs).toBe(true);
  });

  it("shows the data range so runs on different days are told apart", () => {
    const rows = parameterRows([makeRun(1), makeRun(2, { end: "2026-10-14" })]);
    expect(differing(rows).map((row) => row.key)).toEqual(["data"]);
  });
});

describe("metrics", () => {
  it("ranks an infinite profit factor first and skips missing values", () => {
    expect(metricValue(makeMetrics({ profit_factor: null, profit_factor_infinite: true }), "profit_factor")).toBe(Infinity);
    expect(metricValue(makeMetrics({ sharpe: null }), "sharpe")).toBeNull();
  });

  it("marks the highest value, ties included, only when values differ", () => {
    expect(bestIndexes([-12, -5, null, -5])).toEqual(new Set([1, 3]));
    expect(bestIndexes([1, 1])).toEqual(new Set());
    expect(bestIndexes([3, null])).toEqual(new Set());
  });
});

describe("returnCurve", () => {
  it("rebases equity to % return since the first point", () => {
    expect(returnCurve([{ time: "a", value: 200 }, { time: "b", value: 250 }])).toEqual([
      { time: "a", value: 0 },
      { time: "b", value: 25 },
    ]);
    expect(returnCurve([])).toEqual([]);
  });
});
