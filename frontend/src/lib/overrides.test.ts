import { describe, expect, it } from "vitest";

import { config, signals, spec } from "../test/fixtures";
import {
  describeSignal,
  formatTemplate,
  hasProblems,
  pickFields,
  problemOf,
  readOverrides,
  sectionSpecs,
  withOwner,
  withValue,
  writeOverrides,
} from "./overrides";

const period = spec("period", "Period", 20, [2, 300, 1], "int");
const targets = spec("targets_r", "Targets", [2, 3], [0.25, 50, 0.25], "float_list");
const weights = spec("family_weights", "Weights", { trend: 1, breakout: 1.5 }, [-10, 10, 0.5], "weights", {
  keys: ["trend", "breakout"],
});

describe("overrides", () => {
  it("keeps only real changes", () => {
    expect(withValue({}, period, 30)).toEqual({ period: 30 });
    expect(withValue({ period: 30 }, period, 20)).toEqual({});
    expect(withValue({ period: 30 }, period, null)).toEqual({});
    expect(withValue({}, targets, [2, 3])).toEqual({});
    expect(withOwner({ risk: { atr_mult: 3 } }, "risk", {})).toEqual({});
  });

  it("round-trips numbers, lists and weights through the URL", () => {
    const overrides = { risk: { atr_mult: 2.5, targets_r: [1.5, 4] }, scoring: { family_weights: { breakout: 3 } } };
    const params = new URLSearchParams();
    writeOverrides(params, "set", overrides);
    expect(params.toString()).toBe(
      "set.risk.atr_mult=2.5&set.risk.targets_r=1.5%2C4&set.scoring.family_weights.breakout=3",
    );
    expect(readOverrides(params, "set")).toEqual(overrides);
  });

  it("skips what the URL cannot express", () => {
    const params = new URLSearchParams(
      "set.risk.atr_mult=abc&set.risk=1&set.a.b.c.d=1&other.x.y=1&set.scan.fresh_bars=5",
    );
    expect(readOverrides(params, "set")).toEqual({ scan: { fresh_bars: 5 } });
  });

  it("validates values against their declarations", () => {
    expect(problemOf(period, 30)).toBeNull();
    expect(problemOf(period, 2.5)).toBe("Enter a whole number");
    expect(problemOf(period, 1)).toBe("Allowed: 2–300");
    expect(problemOf(targets, [])).toBe("Enter at least one number");
    expect(problemOf(targets, [2, 99])).toBe("Allowed: 0.25–50");
    expect(problemOf(weights, { nope: 1 })).toBe("Unknown key nope");
    expect(problemOf(weights, { breakout: 20 })).toBe("breakout: Allowed: -10–10");
    const specs = sectionSpecs(config.sections);
    expect(hasProblems({ risk: { atr_mult: 3 } }, specs)).toBe(false);
    expect(hasProblems({ risk: { atr_mult: 0 } }, specs)).toBe(true);
    expect(hasProblems({ risk: { bogus: 1 } }, specs)).toBe(true);
  });

  it("picks the listed fields only", () => {
    expect(
      pickFields(
        { risk: { atr_mult: 3, targets_r: [2] }, scan: { fresh_bars: 5 } },
        { risk: ["atr_mult", "atr_period"] },
      ),
    ).toEqual({
      risk: { atr_mult: 3 },
    });
  });

  it("fills description templates like the server does", () => {
    expect(
      formatTemplate("RSI({period}) < {level:g}, close in the top {band:.0%}", { period: 3, level: 15, band: 0.25 }),
    ).toBe("RSI(3) < 15, close in the top 25%");
    const rsi2 = signals.find((signal) => signal.name === "connors_rsi2_long")!;
    expect(describeSignal(rsi2, undefined)).toBe(rsi2.description);
    expect(describeSignal(rsi2, { oversold: 15 })).toBe("RSI(2) < 15 while price is above SMA(200): dip in an uptrend");
  });
});
