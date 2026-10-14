/**
 * Entry and exit rules of a backtest, built from the rule declarations in /api/config, so rules added
 * on the server appear here without frontend changes. A form names its rules and keeps, per rule, only
 * the parameters that differ from the defaults.
 */
import type { ConfigOut, RuleOut } from "../api/client";
import { describeSignal, hasProblems, withOwner, type Overrides, type Values } from "./overrides";

export type RuleDefaults = Pick<ConfigOut, "default_entry" | "default_exits">;
export type RuleSpecs = Pick<ConfigOut, "entry_rules" | "exit_rules">;

export interface TradeRulesForm {
  entry: string;
  /** Parameters of the selected entry rule. */
  entryParams: Values;
  /** Exit rules on top of the initial stop, in the order the server lists them. */
  exits: string[];
  /** Parameters by exit rule name. */
  exitParams: Overrides;
}

export const findRule = (rules: RuleOut[], name: string): RuleOut | undefined => rules.find((rule) => rule.name === name);

/** The rule's description with these values; rules use the same templates as signals. */
export const describeRule = (rule: RuleOut, values: Values | undefined): string => describeSignal(rule, values);

export const sameList = (left: readonly string[], right: readonly string[]): boolean =>
  left.length === right.length && left.every((item, index) => item === right[index]);

/** Exits with one rule switched on or off, kept in the server's order. */
export function toggleExit(exits: readonly string[], name: string, rules: RuleOut[]): string[] {
  const next = exits.includes(name) ? exits.filter((item) => item !== name) : [...exits, name];
  const order = (item: string) => {
    const index = rules.findIndex((rule) => rule.name === item);
    return index < 0 ? rules.length : index;
  };
  return [...next].sort((left, right) => order(left) - order(right));
}

/** How many rule choices and parameters differ from the defaults. */
export function countRuleChanges(form: TradeRulesForm, defaults: RuleDefaults): number {
  const exitParams = Object.entries(form.exitParams).filter(([name]) => form.exits.includes(name));
  return (
    Number(form.entry !== defaults.default_entry) +
    Object.keys(form.entryParams).length +
    Number(!sameList(form.exits, defaults.default_exits)) +
    exitParams.reduce((total, [, values]) => total + Object.keys(values).length, 0)
  );
}

export const defaultRules = (defaults: RuleDefaults): TradeRulesForm => ({
  entry: defaults.default_entry,
  entryParams: {},
  exits: [...defaults.default_exits],
  exitParams: {},
});

/** True when a rule is unknown or a parameter is invalid. */
export function hasRuleProblems(form: TradeRulesForm, specs: RuleSpecs): boolean {
  const entry = findRule(specs.entry_rules, form.entry);
  const exits = form.exits.map((name) => findRule(specs.exit_rules, name));
  if (!entry || exits.some((rule) => !rule)) return true;
  const exitSpecs = Object.fromEntries(exits.map((rule) => [rule!.name, rule!.params]));
  return hasProblems({ [entry.name]: form.entryParams }, { [entry.name]: entry.params }) || hasProblems(form.exitParams, exitSpecs);
}

/** Backtest settings that became exit rule parameters, by setting name. */
const LEGACY_EXIT_SETTINGS: Record<string, string> = { target_r: "target", max_hold_bars: "time" };

/**
 * Moves `backtest.target_r` and `backtest.max_hold_bars` from the settings into the target and time exits,
 * so links and pinned runs from before the trade rules keep working.
 */
export function moveLegacyExitSettings(settings: Overrides, exitParams: Overrides): { settings: Overrides; exitParams: Overrides } {
  const backtest = { ...settings.backtest };
  let params = exitParams;
  for (const [name, rule] of Object.entries(LEGACY_EXIT_SETTINGS)) {
    const value = backtest[name];
    if (value === undefined) continue;
    delete backtest[name];
    params = withOwner(params, rule, { [name]: value, ...params[rule] });
  }
  return { settings: withOwner(settings, "backtest", backtest), exitParams: params };
}
