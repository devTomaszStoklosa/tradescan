/**
 * Reading a run's Monte Carlo: the server resamples its closed trades in R and reports percentiles per method.
 * "Unlucky" and "lucky" are the 5th and 95th percentiles on the side that is worse or better for each value.
 */
import type { MonteCarloMethodOut, MonteCarloOut, PercentilesOut } from "../api/client";

export type MonteCarloValue = "final_return_pct" | "max_drawdown_pct" | "longest_losing_streak";

export type Luck = "unlucky" | "median" | "lucky";

export const LUCK_LABELS: Record<Luck, string> = { unlucky: "Unlucky", median: "Median", lucky: "Lucky" };

/** A higher return and a shallower (less negative) drawdown are better; a longer losing streak is worse. */
export const HIGHER_IS_BETTER: Record<MonteCarloValue, boolean> = {
  final_return_pct: true,
  max_drawdown_pct: true,
  longest_losing_streak: false,
};

/** The percentile that is unlucky, median or lucky for `value`. */
export function percentileFor(percentiles: PercentilesOut, value: MonteCarloValue, luck: Luck): number | null {
  if (luck === "median") return percentiles.p50;
  const low = (luck === "unlucky") === HIGHER_IS_BETTER[value];
  return low ? percentiles.p5 : percentiles.p95;
}

/** True when the run's own order of trades drew down to the ruin level. */
export const actualRuin = (monteCarlo: MonteCarloOut): boolean =>
  monteCarlo.actual.max_drawdown_pct !== null && monteCarlo.actual.max_drawdown_pct <= -monteCarlo.ruin_drawdown_pct;

/** The methods of the given results, each once, in first-seen order. */
export function methodsOf(results: (MonteCarloOut | null)[]): Pick<MonteCarloMethodOut, "name" | "label">[] {
  const seen = new Map<string, string>();
  for (const result of results)
    for (const method of result?.methods ?? []) if (!seen.has(method.name)) seen.set(method.name, method.label);
  return [...seen].map(([name, label]) => ({ name, label }));
}

/** The method shown first: bootstrapping, which spreads the final return too, when there is one. */
export const PREFERRED_METHOD = "bootstrapped";

/** The settings a Monte Carlo ran with, as they are reported. */
export const MONTE_CARLO_SETTINGS = ["simulations", "ruin_drawdown_pct", "seed"] as const;
