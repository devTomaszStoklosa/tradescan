import { describe, expect, it } from "vitest";

import { appliedRule, config, entryRules, exitRules, filterRules, makeMetrics, makeMonteCarlo, makeRun, signals } from "../test/fixtures";
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

  it("shows the Monte Carlo settings of runs that have one", () => {
    const base = makeRun(1);
    const rows = parameterRows([base, makeRun(2, { monteCarlo: makeMonteCarlo({ seed: 7 }) })], config.sections, signals);
    expect(differing(rows)).toEqual([{ key: "monte_carlo.seed", label: "Monte Carlo · Random seed", unit: "", values: ["0", "7"], differs: true }]);
    expect(rows.find((row) => row.key === "monte_carlo.ruin_drawdown_pct")).toMatchObject({ label: "Monte Carlo · Ruin level", unit: "% drawdown" });
    const older = parameterRows([makeRun(1, { monteCarlo: null }), base], config.sections, signals);
    expect(older.find((row) => row.key === "monte_carlo.simulations")).toMatchObject({ values: ["–", "1,000"], differs: true });
    expect(parameterRows([makeRun(1, { monteCarlo: null })]).some((row) => row.key.startsWith("monte_carlo."))).toBe(false);
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

  it("shows the entry and exit rules with their parameters", () => {
    const limit = makeRun(2, { entry: appliedRule(entryRules[2]!, { offset_atr: 1 }), exits: [appliedRule(exitRules[1]!, { max_hold_bars: 5 })] });
    const rows = parameterRows([makeRun(1), limit], config.sections, signals, config);

    expect(differing(rows)).toEqual([
      { key: "entry", label: "Entry", unit: "", values: ["Next open", "Limit order"], differs: true },
      { key: "entry.limit.offset_atr", label: "Limit order · Offset", unit: "ATR", values: ["–", "1"], differs: true },
      { key: "entry.limit.valid_bars", label: "Limit order · Active for", unit: "bars", values: ["–", "1"], differs: true },
      { key: "exits", label: "Exits", unit: "", values: ["Profit target, Time exit", "Time exit"], differs: true },
      { key: "exit.target.target_r", label: "Profit target · Distance", unit: "R", values: ["2", "–"], differs: true },
      { key: "exit.time.max_hold_bars", label: "Time exit · Hold for", unit: "bars", values: ["20", "5"], differs: true },
    ]);
    expect(parameterRows([makeRun(1, { exits: [] })]).find((row) => row.key === "exits")?.values).toEqual(["stop only"]);
  });

  it("shows the entry filters with their parameters, and the benchmark when a run compared one", () => {
    const market = makeRun(2, { filters: [appliedRule(filterRules[1]!, { period: 100 })], benchmark: "QQQ" });
    const rows = parameterRows([makeRun(1), market], config.sections, signals, config);

    expect(differing(rows)).toEqual([
      { key: "filters", label: "Filters", unit: "", values: ["none", "Market filter"], differs: true },
      { key: "benchmark", label: "Benchmark", unit: "", values: ["–", "QQQ"], differs: true },
      { key: "filter.market.period", label: "Market filter · Benchmark SMA", unit: "bars", values: ["–", "100"], differs: true },
    ]);
    expect(parameterRows([makeRun(1)]).some((row) => row.key === "benchmark")).toBe(false);
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
