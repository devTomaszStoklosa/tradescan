/** Checks and resets of a backtest setup, shared by the Backtest, Sweep and Watchlist forms. */
import type { ConfigOut, SignalOut } from "../api/client";
import { BACKTEST_SECTIONS } from "./choices";
import { countChanges, hasProblems, pickSections, sectionSpecs } from "./overrides";
import { rulesBody, type BacktestRules } from "./params";
import { countRuleChanges, defaultRules, hasRuleProblems } from "./rules";

/** How many settings, signal parameters, trade rules and the benchmark differ from the defaults. */
export function setupChanges(setup: BacktestRules, config: ConfigOut): number {
  return (
    countChanges(setup.settings) +
    Object.keys(setup.signalParams).length +
    countRuleChanges(setup, config) +
    Number(setup.benchmark.trim() !== "")
  );
}

/**
 * True while the signal or, in a setup that has one, the ticker is missing, or any value is invalid.
 * A setting outside `sectionNames`, the sections the page offers, counts as invalid.
 */
export function hasSetupProblems(
  setup: BacktestRules & { ticker?: string },
  config: ConfigOut,
  signals: SignalOut[],
  sectionNames: readonly string[] = BACKTEST_SECTIONS,
): boolean {
  const sections = pickSections(config.sections, sectionNames);
  const selected = signals.find((signal) => signal.name === setup.signal);
  return (
    setup.ticker?.trim() === "" ||
    !rulesBody(setup) ||
    hasProblems(setup.settings, sectionSpecs(sections)) ||
    hasRuleProblems(setup, config) ||
    (selected !== undefined && hasProblems({ [selected.name]: setup.signalParams }, { [selected.name]: selected.params }))
  );
}

/** The setup with every setting, signal parameter, trade rule and the benchmark back at its default. */
export function resetSetup<T extends BacktestRules>(setup: T, config: ConfigOut): T {
  return { ...setup, settings: {}, signalParams: {}, ...defaultRules(config), benchmark: "" };
}
