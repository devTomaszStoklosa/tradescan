/**
 * Portfolio backtest: one setup on every ticker of a watchlist with one shared equity. The form and its URL, the
 * request, and links to the same setup on other pages.
 *
 * The URL holds the universe (`w=<watchlist>` or `t=<tickers>`), the setup with the Backtest page's keys apart from
 * the ticker (the max positions and the max exposure are settings, `set.portfolio.<name>`), the engines (`eng`), and
 * the priority rule (`prio=<rule>`, left out for the default) with its parameters (`pr.<rule>.<name>`). A rule that
 * scores like the scanner reads the scanner's settings too, with the Scan page's keys (`set.scoring.<name>`, ...).
 */
import type { ConfigOut, PortfolioIn, RuleIn, SettingsSectionOut } from "../api/client";
import { PORTFOLIO_PAGE_SECTIONS, PORTFOLIO_SECTION, SCORE_FIELDS, SCORE_SECTIONS } from "./choices";
import { hasProblems, readOverrides, writeOverrides, type Overrides, type Values } from "./overrides";
import { readBacktestRules, readUniverse, rulesBody, universeBody, writeBacktestForm, writeBacktestSetup, writeUniverse, type BacktestRules, type Universe } from "./params";
import { findRule, type RuleDefaults } from "./rules";
import { resetSetup } from "./setup";
import { writeWatchlistForm } from "./watchlistBacktest";

export const PRIORITY_PREFIX = "pr";

export type PortfolioDefaults = RuleDefaults & Pick<ConfigOut, "default_priority" | "priority_rules">;

export interface PortfolioForm extends BacktestRules {
  universe: Universe;
  engines: string[];
  priority: string;
  /** Parameters of the selected priority rule. */
  priorityParams: Values;
}

const engineList = (value: string | null): string[] =>
  (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

/** The settings sections the priority rule reads: the scanner's for a rule that scores like the scanner, else none. */
export const prioritySections = (priority: string, config: Pick<ConfigOut, "priority_rules">): readonly string[] =>
  findRule(config.priority_rules, priority)?.needs_scan ? SCORE_SECTIONS : [];

/** The settings sections the form offers: the setup's, the portfolio's and those its priority rule reads. */
export const portfolioSections = (form: Pick<PortfolioForm, "priority">, config: Pick<ConfigOut, "priority_rules">): string[] => [
  ...PORTFOLIO_PAGE_SECTIONS,
  ...prioritySections(form.priority, config),
];

/** Of the scanner's sections, the parameters the score does not read, by section, for the fields to leave out. */
export const scoreExclusions = (sections: SettingsSectionOut[]): Record<string, string[]> =>
  Object.fromEntries(
    sections.map((section) => {
      const read = SCORE_FIELDS[section.name];
      return [section.name, read ? section.params.map((spec) => spec.name).filter((name) => !read.includes(name)) : []];
    }),
  );

/** The scanner's settings, unless the priority rule reads them. */
function withoutUnreadSettings(settings: Overrides, priority: string, config: Pick<ConfigOut, "priority_rules">): Overrides {
  const read = prioritySections(priority, config);
  return Object.fromEntries(Object.entries(settings).filter(([owner]) => !SCORE_SECTIONS.includes(owner) || read.includes(owner)));
}

/** The form with this priority rule and its parameters; the scanner's settings go when the rule does not read them. */
export const choosePriority = (form: PortfolioForm, priority: string, priorityParams: Values, config: Pick<ConfigOut, "priority_rules">): PortfolioForm => ({
  ...form,
  priority,
  priorityParams,
  settings: withoutUnreadSettings(form.settings, priority, config),
});

/** Rules the URL leaves out are the server's defaults. */
export function readPortfolioForm(params: URLSearchParams, defaults: PortfolioDefaults): PortfolioForm {
  const engines = engineList(params.get("eng"));
  const priority = params.get("prio") || defaults.default_priority;
  const rules = readBacktestRules(params, defaults);
  return {
    universe: readUniverse(params),
    ...rules,
    settings: withoutUnreadSettings(rules.settings, priority, defaults),
    engines: engines.length ? engines : ["vectorized"],
    priority,
    priorityParams: readOverrides(params, PRIORITY_PREFIX)[priority] ?? {},
  };
}

/** With `defaults`, rules equal to them are left out, so unchanged links stay short. */
export function writePortfolioForm(form: PortfolioForm, defaults?: PortfolioDefaults): URLSearchParams {
  const params = new URLSearchParams();
  writeUniverse(params, form.universe);
  for (const [key, value] of writeBacktestSetup(form, defaults, form.engines)) params.append(key, value);
  if (form.priority !== defaults?.default_priority) params.set("prio", form.priority);
  writeOverrides(params, PRIORITY_PREFIX, { [form.priority]: form.priorityParams });
  return params;
}

/** The request without the account, which the page adds from browser storage; null until a universe, a signal and an engine are chosen. */
export function portfolioBody(form: PortfolioForm): PortfolioIn | null {
  const universe = universeBody(form.universe);
  const rules = rulesBody(form);
  if (!universe || !rules || !form.engines.length) return null;
  return { ...universe, ...rules, engines: form.engines, priority: { name: form.priority, params: form.priorityParams as RuleIn["params"] } };
}

/** How many of the priority rule's choices differ from the defaults. */
export const priorityChanges = (form: PortfolioForm, defaults: PortfolioDefaults): number =>
  Number(form.priority !== defaults.default_priority) + Object.keys(form.priorityParams).length;

/** True when the priority rule is unknown or one of its parameters is invalid. */
export function hasPriorityProblems(form: PortfolioForm, config: Pick<ConfigOut, "priority_rules">): boolean {
  const rule = findRule(config.priority_rules, form.priority);
  return !rule || hasProblems({ [rule.name]: form.priorityParams }, { [rule.name]: rule.params });
}

/** The form with the setup and the priority rule back at their defaults; the universe and the engines stay. */
export const resetPortfolio = (form: PortfolioForm, config: ConfigOut): PortfolioForm => ({
  ...resetSetup(form, config),
  priority: config.default_priority,
  priorityParams: {},
});

/** The setup without what only a portfolio has: the universe, the engines, the priority and the settings of the
 * portfolio and of the scanner's score. */
function setupOf(form: PortfolioForm): BacktestRules {
  const { universe: _universe, engines: _engines, priority: _priority, priorityParams: _priorityParams, settings, ...rules } = form;
  const setupSettings = Object.fromEntries(
    Object.entries(settings).filter(([owner]) => owner !== PORTFOLIO_SECTION && !SCORE_SECTIONS.includes(owner)),
  );
  return { ...rules, settings: setupSettings };
}

/** The Backtest page link for one ticker of the result, with the benchmark the run's filters compared. */
export function backtestLink(form: PortfolioForm, ticker: string, engine: string, benchmark: string | null, config: ConfigOut): string {
  const setup = setupOf(form);
  return `/backtest?${writeBacktestForm({ ...setup, ticker, benchmark: benchmark ?? setup.benchmark, engines: [engine] }, config).toString()}`;
}

/** The Watchlist page link: the same setup on every ticker on its own, with its own equity. */
export function watchlistLink(form: PortfolioForm, config: ConfigOut): string {
  return `/watchlist?${writeWatchlistForm({ ...setupOf(form), universe: form.universe }, config).toString()}`;
}
