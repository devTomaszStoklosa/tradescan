import { describe, expect, it } from "vitest";

import { backtestForm, config, signals } from "../test/fixtures";
import { newSweepForm } from "./sweep";
import {
  backtestLink,
  readWalkForwardForm,
  resetWalkForward,
  walkForwardBody,
  walkForwardChanges,
  walkForwardParams,
  walkForwardRuns,
  windowCount,
  writeWalkForwardForm,
  type WalkForwardForm,
} from "./walkForward";

const form: WalkForwardForm = {
  ...newSweepForm(backtestForm),
  axes: [
    { key: "signal.oversold", from: 5, to: 15, step: 5 },
    { key: "exit.target.target_r", from: 2, to: 3, step: 1 },
  ],
  scheme: "rolling",
  metric: "sharpe",
};
const params = walkForwardParams(form, config, signals);

describe("walk-forward form", () => {
  it("round-trips through the URL, leaving the default scheme and metric out", () => {
    const changed: WalkForwardForm = {
      ...form,
      scheme: "anchored",
      metric: "expectancy_r",
      settings: { walk_forward: { windows: 8 } },
    };
    const url = writeWalkForwardForm(changed, config);
    expect(url.get("scheme")).toBe("anchored");
    expect(url.get("wm")).toBe("expectancy_r");
    expect(url.get("set.walk_forward.windows")).toBe("8");
    expect(readWalkForwardForm(url, config)).toEqual(changed);

    const plain = writeWalkForwardForm(form, config);
    expect(plain.has("scheme") || plain.has("wm")).toBe(false);
    expect(readWalkForwardForm(plain, config)).toEqual(form);
  });

  it("falls back to the defaults for an unknown scheme or metric and drops the out-of-sample share", () => {
    const url = new URLSearchParams(
      "ticker=SPY&signal=connors_rsi2_long&scheme=expanding&wm=trades&set.backtest.oos_pct=20&set.backtest.commission_pct=0.2",
    );
    const read = readWalkForwardForm(url, config);
    expect([read.scheme, read.metric]).toEqual(["rolling", "sharpe"]);
    expect(read.settings).toEqual({ backtest: { commission_pct: 0.2 } });
    expect(readWalkForwardForm(new URLSearchParams("ticker=SPY&set.backtest.oos_pct=20"), config).settings).toEqual({});
  });

  it("offers a sweep's parameters except the settings its windows fix", () => {
    const keys = params.map((item) => item.key);
    expect(keys).toContain("settings.backtest.commission_pct");
    expect(keys).not.toContain("settings.backtest.oos_pct");
    const fixed = {
      ...config,
      walk_forward: { ...config.walk_forward, fixed: [...config.walk_forward.fixed, "risk.atr_mult"] },
    };
    expect(walkForwardParams(form, fixed, signals).map((item) => item.key)).not.toContain("settings.risk.atr_mult");
    expect(keys).toContain("settings.risk.atr_mult");
  });

  it("counts and resets the changed settings, scheme and metric", () => {
    const changed: WalkForwardForm = {
      ...form,
      scheme: "anchored",
      metric: "sqn",
      settings: { walk_forward: { min_trades: 5 } },
    };
    expect(walkForwardChanges(form, config)).toBe(0);
    expect(walkForwardChanges(changed, config)).toBe(3);
    expect(resetWalkForward(changed, config)).toEqual(form);
  });
});

describe("walk-forward request", () => {
  it("counts a backtest per combination and in-sample window, the next one included", () => {
    expect(windowCount(form, config)).toBe(5);
    expect(walkForwardRuns(form, params, config)).toEqual({ combinations: 6, windows: 6, runs: 36 });
    const eight = { ...form, settings: { walk_forward: { windows: 8 } } };
    expect(walkForwardRuns(eight, params, config)).toEqual({ combinations: 6, windows: 9, runs: 54 });
    expect(
      walkForwardRuns({ ...form, axes: [{ key: "signal.oversold", from: 5, to: null, step: 5 }] }, params, config),
    ).toBeNull();
  });

  it("is the sweep request with the scheme and the metric, within both caps", () => {
    expect(walkForwardBody({ ...form, scheme: "anchored", metric: "sqn" }, params, config)).toMatchObject({
      ticker: "SPY",
      signal: "connors_rsi2_long",
      scheme: "anchored",
      metric: "sqn",
      axes: [
        { target: "signal", owner: null, name: "oversold", values: [5, 10, 15] },
        { target: "exit", owner: "target", name: "target_r", values: [2, 3] },
      ],
    });
    const capped = { ...config, walk_forward: { ...config.walk_forward, max_runs: 30 } };
    expect(walkForwardBody(form, params, capped)).toBeNull();
    expect(walkForwardBody({ ...form, axes: [] }, params, config)).toBeNull();
  });

  it("opens a pick on the Backtest page without the walk-forward's settings", () => {
    const withWindows = { ...form, settings: { walk_forward: { windows: 8 }, risk: { atr_mult: 3 } } };
    const axisParams = ["signal.oversold", "exit.target.target_r"].map((key) =>
      params.find((item) => item.key === key)!,
    );
    expect(backtestLink(withWindows, axisParams, [15, 3], config).toString()).toBe(
      "ticker=SPY&signal=connors_rsi2_long&eng=vectorized&set.risk.atr_mult=3&sig.connors_rsi2_long.oversold=15&ex.target.target_r=3",
    );
  });
});
