import { describe, expect, it } from "vitest";

import { backtestForm, config, signals, sweepResult } from "../test/fixtures";
import {
  aboveBreakEven,
  axisValues,
  bestCell,
  combinations,
  defaultAxis,
  heatScale,
  median,
  neighbourAverage,
  neighbours,
  newSweepForm,
  readSweepForm,
  shade,
  sweepBody,
  sweepParams,
  withCombination,
  writeSweepForm,
  type SweepForm,
  type SweepParam,
} from "./sweep";

const limits = config.sweep;
const setup = newSweepForm(backtestForm);
const params = sweepParams(setup, config, signals);
const param = (key: string): SweepParam => {
  const found = params.find((item) => item.key === key);
  if (!found) throw new Error(`no parameter ${key}`);
  return found;
};

describe("sweepParams", () => {
  it("offers the single-number parameters the Backtest form shows, grouped by what holds them", () => {
    expect(params.map((item) => item.key)).toEqual([
      "signal.rsi_period",
      "signal.trend_period",
      "signal.oversold",
      "exit.target.target_r",
      "exit.time.max_hold_bars",
      "settings.risk.atr_period",
      "settings.risk.atr_mult",
      "settings.backtest.commission_pct",
      "settings.backtest.slippage_pct",
      "settings.pyramid.max_units",
      "settings.pyramid.add_every_atr",
    ]);
    expect(param("exit.target.target_r")).toMatchObject({
      target: "exit",
      owner: "target",
      name: "target_r",
      group: "Exit: Profit target",
      current: 2,
    });
    expect(param("settings.risk.atr_mult").group).toBe("Risk plan");
    expect(param("settings.pyramid.max_units")).toMatchObject({
      target: "settings",
      owner: "pyramid",
      group: "Pyramiding",
      current: 1,
    });
  });

  it("follows the setup: its entry, its exits and its changed values", () => {
    const changed = sweepParams(
      {
        ...setup,
        entry: "limit",
        exits: ["time"],
        signalParams: { oversold: 15 },
        settings: { risk: { atr_mult: 3 } },
      },
      config,
      signals,
    );
    const keys = changed.map((item) => item.key);
    expect(keys).toContain("entry.offset_atr");
    expect(keys).not.toContain("exit.target.target_r");
    expect(changed.find((item) => item.key === "signal.oversold")?.current).toBe(15);
    expect(changed.find((item) => item.key === "settings.risk.atr_mult")?.current).toBe(3);
  });
});

describe("sweepParams with entry filters", () => {
  it("offers the parameters of the chosen filters after the signal's", () => {
    const filtered = sweepParams(
      { ...setup, filters: ["trend"], filterParams: { trend: { period: 100 } } },
      config,
      signals,
    );
    expect(filtered.map((item) => item.key).slice(2, 5)).toEqual([
      "signal.oversold",
      "filter.trend.period",
      "exit.target.target_r",
    ]);
    const trend = filtered.find((item) => item.key === "filter.trend.period");
    expect(trend).toMatchObject({
      target: "filter",
      owner: "trend",
      name: "period",
      group: "Filter: Trend filter",
      current: 100,
    });
    expect(withCombination({ ...setup, filters: ["trend"] }, [trend!], [150]).filterParams).toEqual({
      trend: { period: 150 },
    });
  });
});

describe("axis ranges", () => {
  it("centres a default range on the setup's value in the declared steps", () => {
    expect(defaultAxis(param("signal.oversold"))).toEqual({ key: "signal.oversold", from: 6, to: 14, step: 1 });
    expect(defaultAxis(param("exit.target.target_r"))).toEqual({
      key: "exit.target.target_r",
      from: 1,
      to: 3,
      step: 0.25,
    });
  });

  it("shifts a default range that would leave the declared limits", () => {
    expect(defaultAxis(param("signal.rsi_period"))).toMatchObject({ from: 2, to: 10 });
    expect(defaultAxis({ ...param("signal.oversold"), current: 48 })).toMatchObject({ from: 42, to: 50 });
  });

  it("lists the values without float noise", () => {
    const range = axisValues(
      { key: "x", from: 0.1, to: 0.7, step: 0.2 },
      param("settings.backtest.commission_pct").spec,
      limits,
    );
    expect(range.values).toEqual([0.1, 0.3, 0.5, 0.7]);
    expect(
      axisValues({ key: "x", from: 1, to: 3, step: 0.25 }, param("exit.target.target_r").spec, limits).values,
    ).toHaveLength(9);
  });

  it.each([
    [{ from: null, to: 5, step: 1 }, "Enter From, To and Step"],
    [{ from: 5, to: 10, step: 0 }, "Step must be above 0"],
    [{ from: 10, to: 5, step: 1 }, "To must not be below From"],
    [{ from: 0, to: 5, step: 1 }, "Allowed: 1–50"],
    [{ from: 5, to: 5, step: 1 }, "at least 2 values"],
    [{ from: 1, to: 50, step: 0.5 }, "99 values: at most 50"],
  ])("explains a bad range %o", (axis, problem) => {
    expect(axisValues({ key: "signal.oversold", ...axis }, param("signal.oversold").spec, limits).problem).toContain(
      problem,
    );
  });

  it("wants whole numbers for whole-number parameters", () => {
    expect(axisValues({ key: "x", from: 2, to: 5, step: 0.5 }, param("signal.rsi_period").spec, limits).problem).toBe(
      "Use whole numbers",
    );
  });

  it("multiplies the value counts", () => {
    const ranges = [
      axisValues({ key: "a", from: 1, to: 3, step: 1 }, param("signal.oversold").spec, limits),
      { values: [1, 2], problem: null },
    ];
    expect(combinations(ranges)).toBe(6);
    expect(combinations([...ranges, { values: null, problem: "bad" }])).toBeNull();
  });
});

describe("sweep form", () => {
  const form: SweepForm = {
    ...setup,
    signalParams: { rsi_period: 3 },
    axes: [
      { key: "signal.oversold", from: 5, to: 15, step: 5 },
      { key: "exit.target.target_r", from: 1.5, to: 3, step: 0.5 },
    ],
  };

  it("leaves a backtest's Monte Carlo settings behind, since a sweep runs none", () => {
    const settings = { risk: { atr_mult: 3 }, monte_carlo: { seed: 7 } };
    expect(newSweepForm({ ...backtestForm, settings }).settings).toEqual({ risk: { atr_mult: 3 } });
  });

  it("round-trips through the URL with the backtest setup's keys", () => {
    const url = writeSweepForm(form, config);
    expect(url.toString()).toBe(
      "ticker=SPY&signal=connors_rsi2_long&sig.connors_rsi2_long.rsi_period=3&ax1=signal.oversold&ax1v=5%3A15%3A5&ax2=exit.target.target_r&ax2v=1.5%3A3%3A0.5",
    );
    expect(url.has("eng")).toBe(false);
    expect(readSweepForm(url, config)).toEqual(form);
  });

  it("builds the request from the axes' values", () => {
    const body = sweepBody(form, sweepParams(form, config, signals), limits);
    expect(body).toMatchObject({ ticker: "SPY", signal: "connors_rsi2_long", params: { rsi_period: 3 } });
    expect(body?.axes).toEqual([
      { target: "signal", owner: null, name: "oversold", values: [5, 10, 15] },
      { target: "exit", owner: "target", name: "target_r", values: [1.5, 2, 2.5, 3] },
    ]);
    expect(body).not.toHaveProperty("engines");
  });

  it("sends nothing while an axis is unknown, invalid or the grid too large", () => {
    const check = (axes: SweepForm["axes"]) => sweepBody({ ...form, axes }, params, limits);
    expect(check([])).toBeNull();
    expect(check([{ key: "entry.offset_atr", from: 0, to: 1, step: 0.5 }])).toBeNull();
    expect(check([{ key: "signal.oversold", from: 15, to: 5, step: 5 }])).toBeNull();
    expect(
      check([
        { key: "signal.oversold", from: 1, to: 15, step: 1 },
        { key: "exit.time.max_hold_bars", from: 1, to: 15, step: 1 },
      ]),
    ).toBeNull();
  });

  it("applies a combination to the setup, dropping values equal to the defaults", () => {
    const axisParams = [param("signal.oversold"), param("exit.target.target_r"), param("settings.risk.atr_mult")];
    const next = withCombination(setup, axisParams, [15, 2, 3]);
    expect(next.signalParams).toEqual({ oversold: 15 });
    expect(next.exitParams).toEqual({});
    expect(next.settings).toEqual({ risk: { atr_mult: 3 } });
  });
});

describe("sweep results", () => {
  const { cells } = sweepResult;
  const counts = [3, 2];

  it("colours around break-even with one scale for both periods", () => {
    const scale = heatScale(cells, "sharpe");
    expect(scale).toEqual({ kind: "diverging", center: 0, extent: 1.4 });
    expect(shade(0.7, scale)).toEqual({ tone: "good", strength: 0.5 });
    expect(shade(-0.2, scale)?.tone).toBe("bad");
    expect(shade(null, scale)).toBeNull();
    expect(heatScale(cells, "trades")).toEqual({ kind: "sequential", min: 8, max: 30 });
    expect(shade(19, heatScale(cells, "trades"))).toEqual({ tone: "level", strength: 0.5 });
  });

  it("finds the best in-sample cell, skipping cells that could not run", () => {
    expect(bestCell(cells, "sharpe")).toBe(3);
    expect(bestCell(cells, "sharpe", "out_of_sample")).toBe(2);
  });

  it("summarises a period", () => {
    expect(median([3, 1, 2])).toBe(2);
    expect(median([4, 1, 2, 3])).toBe(2.5);
    expect(median([])).toBeNull();
    expect(aboveBreakEven(cells, "out_of_sample", "sharpe")).toBe(0.8);
    expect(aboveBreakEven(cells, "out_of_sample", "trades")).toBeNull();
  });

  it("averages the neighbouring settings", () => {
    expect(neighbours(0, counts).sort()).toEqual([1, 2, 3]);
    expect(neighbours(3, counts).sort()).toEqual([0, 1, 2, 4, 5]);
    expect(neighbours(1, [4])).toEqual([0, 2]);
    // Cell 3's neighbours in-sample: 0.4, 0.6, 0.9, 0.7 and the failed cell, which is skipped.
    expect(neighbourAverage(cells, 3, counts, "in_sample", "sharpe")).toBeCloseTo(0.65);
  });
});
