/** Checks and resets of a backtest setup, shared by the Backtest and the Sweep form. */
import type { ConfigOut, SignalOut } from "../api/client";
import { BACKTEST_SECTIONS } from "./choices";
import { countChanges, hasProblems, pickSections, sectionSpecs } from "./overrides";
import { setupBody, type BacktestSetup } from "./params";
import { countRuleChanges, defaultRules, hasRuleProblems } from "./rules";

/** How many settings, signal parameters and trade rules differ from the defaults. */
export function setupChanges(setup: BacktestSetup, config: ConfigOut): number {
  return countChanges(setup.settings) + Object.keys(setup.signalParams).length + countRuleChanges(setup, config);
}

/** True while the ticker or signal is missing or any value is invalid. */
export function hasSetupProblems(setup: BacktestSetup, config: ConfigOut, signals: SignalOut[]): boolean {
  const sections = pickSections(config.sections, BACKTEST_SECTIONS);
  const selected = signals.find((signal) => signal.name === setup.signal);
  return (
    !setupBody(setup) ||
    hasProblems(setup.settings, sectionSpecs(sections)) ||
    hasRuleProblems(setup, config) ||
    (selected !== undefined && hasProblems({ [selected.name]: setup.signalParams }, { [selected.name]: selected.params }))
  );
}

/** The setup with every setting, signal parameter and trade rule back at its default. */
export function resetSetup<T extends BacktestSetup>(setup: T, config: ConfigOut): T {
  return { ...setup, settings: {}, signalParams: {}, ...defaultRules(config) };
}
