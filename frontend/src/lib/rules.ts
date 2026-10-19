/**
 * Entry filters, entry and exit rules of a backtest, built from the rule declarations in /api/config, so
 * rules added on the server appear here without frontend changes. A form names its rules and keeps, per
 * rule, only the parameters that differ from the defaults. A backtest uses no filters unless it names them.
 */
import type { ConfigOut, FilterRuleOut, RuleOut } from "../api/client";
import { describeSignal, hasProblems, withOwner, type Overrides, type Values } from "./overrides";
import { omit } from "./records";

export type RuleDefaults = Pick<ConfigOut, "default_entry" | "default_exits">;
export type RuleSpecs = Pick<ConfigOut, "entry_rules" | "exit_rules" | "filter_rules">;

export interface TradeRulesForm {
  entry: string;
  /** Parameters of the selected entry rule. */
  entryParams: Values;
  /** Exit rules on top of the initial stop, in the order the server lists them. */
  exits: string[];
  /** Parameters by exit rule name. */
  exitParams: Overrides;
  /** Entry filters a signal has to pass, in the order the server lists them. */
  filters: string[];
  /** Parameters by filter name. */
  filterParams: Overrides;
}

export const findRule = <T extends RuleOut>(rules: T[], name: string): T | undefined =>
  rules.find((rule) => rule.name === name);

/** The rule's description with these values; rules use the same templates as signals. */
export const describeRule = (rule: RuleOut, values: Values | undefined): string => describeSignal(rule, values);

export const sameList = (left: readonly string[], right: readonly string[]): boolean =>
  left.length === right.length && left.every((item, index) => item === right[index]);

/** Chosen exits or filters with one rule switched on or off, kept in the server's order. */
export function toggleRule(chosen: readonly string[], name: string, rules: RuleOut[]): string[] {
  const next = chosen.includes(name) ? chosen.filter((item) => item !== name) : [...chosen, name];
  const order = (item: string) => {
    const index = rules.findIndex((rule) => rule.name === item);
    return index < 0 ? rules.length : index;
  };
  return [...next].sort((left, right) => order(left) - order(right));
}

/** How many changed parameters the chosen rules have. */
const countParams = (params: Overrides, chosen: readonly string[]): number =>
  Object.entries(params)
    .filter(([name]) => chosen.includes(name))
    .reduce((total, [, values]) => total + Object.keys(values).length, 0);

/** How many rule choices and parameters differ from the defaults. */
export function countRuleChanges(form: TradeRulesForm, defaults: RuleDefaults): number {
  return (
    Number(form.filters.length > 0) +
    countParams(form.filterParams, form.filters) +
    Number(form.entry !== defaults.default_entry) +
    Object.keys(form.entryParams).length +
    Number(!sameList(form.exits, defaults.default_exits)) +
    countParams(form.exitParams, form.exits)
  );
}

export const defaultRules = (defaults: RuleDefaults): TradeRulesForm => ({
  entry: defaults.default_entry,
  entryParams: {},
  exits: [...defaults.default_exits],
  exitParams: {},
  filters: [],
  filterParams: {},
});

/** True when a chosen filter compares the benchmark, so the backtest needs one. */
export const needsBenchmark = (filters: readonly string[], rules: FilterRuleOut[]): boolean =>
  filters.some((name) => findRule(rules, name)?.needs_benchmark);

const allFound = <T>(rules: (T | undefined)[]): rules is T[] => rules.every((rule) => rule !== undefined);

/** True when a rule is unknown or a parameter is invalid. */
export function hasRuleProblems(form: TradeRulesForm, specs: RuleSpecs): boolean {
  const entry = findRule(specs.entry_rules, form.entry);
  const exits = form.exits.map((name) => findRule(specs.exit_rules, name));
  const filters = form.filters.map((name) => findRule(specs.filter_rules, name));
  if (!entry || !allFound(exits) || !allFound(filters)) return true;
  const specsOf = (rules: RuleOut[]) => Object.fromEntries(rules.map((rule) => [rule.name, rule.params]));
  return (
    hasProblems({ [entry.name]: form.entryParams }, { [entry.name]: entry.params }) ||
    hasProblems(form.exitParams, specsOf(exits)) ||
    hasProblems(form.filterParams, specsOf(filters))
  );
}

/** Backtest settings that became exit rule parameters, by setting name. */
const LEGACY_EXIT_SETTINGS: Record<string, string> = { target_r: "target", max_hold_bars: "time" };

/**
 * Moves `backtest.target_r` and `backtest.max_hold_bars` from the settings into the target and time exits,
 * so links and pinned runs from before the trade rules keep working.
 */
export function moveLegacyExitSettings(
  settings: Overrides,
  exitParams: Overrides,
): { settings: Overrides; exitParams: Overrides } {
  let backtest = { ...settings.backtest };
  let params = exitParams;
  for (const [name, rule] of Object.entries(LEGACY_EXIT_SETTINGS)) {
    const value = backtest[name];
    if (value === undefined) continue;
    backtest = omit(backtest, name);
    params = withOwner(params, rule, { [name]: value, ...params[rule] });
  }
  return { settings: withOwner(settings, "backtest", backtest), exitParams: params };
}
