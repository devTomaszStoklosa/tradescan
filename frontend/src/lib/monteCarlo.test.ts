import { describe, expect, it } from "vitest";

import { makeMonteCarlo } from "../test/fixtures";
import { actualRuin, methodsOf, percentileFor } from "./monteCarlo";

const percentiles = { p5: 1, p25: 2, p50: 3, p75: 4, p95: 5 };

describe("percentileFor", () => {
  it("takes the low end as unlucky when higher is better", () => {
    expect(percentileFor(percentiles, "final_return_pct", "unlucky")).toBe(1);
    expect(percentileFor(percentiles, "max_drawdown_pct", "lucky")).toBe(5);
    expect(percentileFor(percentiles, "final_return_pct", "median")).toBe(3);
  });

  it("takes the high end as unlucky for losing streaks", () => {
    expect(percentileFor(percentiles, "longest_losing_streak", "unlucky")).toBe(5);
    expect(percentileFor(percentiles, "longest_losing_streak", "lucky")).toBe(1);
  });
});

describe("actualRuin", () => {
  it("is reached by a drawdown at least as deep as the ruin level", () => {
    const actual = makeMonteCarlo().actual;
    expect(actualRuin(makeMonteCarlo({ ruin_drawdown_pct: 6.2 }))).toBe(true);
    expect(actualRuin(makeMonteCarlo({ ruin_drawdown_pct: 10 }))).toBe(false);
    expect(actualRuin(makeMonteCarlo({ actual: { ...actual, max_drawdown_pct: null } }))).toBe(false);
  });
});

describe("methodsOf", () => {
  it("lists every method once, in first-seen order, skipping runs without a Monte Carlo", () => {
    const [shuffled, bootstrapped] = makeMonteCarlo().methods;
    const results = [null, makeMonteCarlo({ methods: [bootstrapped!] }), makeMonteCarlo()];
    expect(methodsOf(results)).toEqual([
      { name: "bootstrapped", label: "Bootstrapped" },
      { name: shuffled!.name, label: "Shuffled" },
    ]);
    expect(methodsOf([null])).toEqual([]);
  });
});
