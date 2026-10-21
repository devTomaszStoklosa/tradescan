/**
 * Momentum rotation: hold the strongest tickers of a watchlist, rebalanced weekly or monthly. The form, its URL and
 * the request.
 *
 * The URL holds the universe (`w=<watchlist>` or `t=<tickers>`), the engines (`eng=<engine>,<engine>`, left out for
 * the vectorized engine alone), the history (`p=`), the ranking rule (`rank=<rule>`,
 * left out for the default) with its parameters (`rk.<rule>.<name>`), the weighting rule (`wt=<rule>`, left out for
 * the default) with its parameters (`wp.<rule>.<name>`), the rebalance (`reb=weekly`, left out for monthly), the safe
 * asset (`safe=<ticker>`, left out for cash), the buy & hold benchmark (`b=<ticker>`) and the settings of the
 * rotation and the costs (`set.rotation.<name>`, `set.backtest.<name>`).
 */
import type { ConfigOut, Rebalance, RotationIn, RuleIn } from "../api/client";
import { PERIODS, ROTATION_PAGE_SECTIONS } from "./choices";
import {
  countChanges,
  hasProblems,
  pickOwners,
  pickSections,
  readOverrides,
  sectionSpecs,
  SETTINGS_PREFIX,
  writeOverrides,
  type Overrides,
  type Values,
} from "./overrides";
import { readUniverse, tickerList, universeBody, writeUniverse, type Universe } from "./params";
import { findRule } from "./rules";

export const RANKING_PREFIX = "rk";
export const WEIGHTING_PREFIX = "wp";
/** The server's rebalance when a request names none. */
export const DEFAULT_REBALANCE: Rebalance = "monthly";
/** The server's engines when a request names none. */
export const DEFAULT_ENGINES = ["vectorized"];

export type RotationDefaults = Pick<
  ConfigOut,
  "default_ranking" | "ranking_rules" | "default_weighting" | "weight_rules"
>;

export interface RotationForm {
  universe: Universe;
  /** Engines that run the rotation; Cerebro checks the vectorized engine. */
  engines: string[];
  /** History to load; empty for the server's default. */
  period: string;
  ranking: string;
  /** Parameters of the selected ranking rule. */
  rankingParams: Values;
  weighting: string;
  /** Parameters of the selected weighting rule. */
  weightingParams: Values;
  rebalance: Rebalance;
  /** Takes the slots of picks whose absolute momentum fails; empty for cash. */
  safeAsset: string;
  /** Compared by buy & hold; empty for the watchlist's or the server's default. */
  benchmark: string;
  settings: Overrides;
}

const ticker = (value: string | null): string => (value ?? "").trim().toUpperCase();

const rebalanceOf = (value: string | null): Rebalance => (value === "weekly" ? "weekly" : DEFAULT_REBALANCE);

const engineList = (value: string | null): string[] =>
  (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

/** Rules the URL leaves out are the server's defaults; settings of other sections are left out. */
export function readRotationForm(params: URLSearchParams, defaults: RotationDefaults): RotationForm {
  const ranking = params.get("rank") || defaults.default_ranking;
  const weighting = params.get("wt") || defaults.default_weighting;
  const engines = engineList(params.get("eng"));
  return {
    universe: readUniverse(params),
    engines: engines.length ? engines : [...DEFAULT_ENGINES],
    period: params.get("p") ?? "",
    ranking,
    rankingParams: readOverrides(params, RANKING_PREFIX)[ranking] ?? {},
    weighting,
    weightingParams: readOverrides(params, WEIGHTING_PREFIX)[weighting] ?? {},
    rebalance: rebalanceOf(params.get("reb")),
    safeAsset: ticker(params.get("safe")),
    benchmark: ticker(params.get("b")),
    settings: pickOwners(readOverrides(params, SETTINGS_PREFIX), ROTATION_PAGE_SECTIONS),
  };
}

/** With `defaults`, rules equal to them are left out, so unchanged links stay short. */
export function writeRotationForm(form: RotationForm, defaults?: RotationDefaults): URLSearchParams {
  const params = new URLSearchParams();
  writeUniverse(params, form.universe);
  if (form.engines.join(",") !== DEFAULT_ENGINES.join(",")) params.set("eng", form.engines.join(","));
  if (form.period) params.set("p", form.period);
  if (form.ranking !== defaults?.default_ranking) params.set("rank", form.ranking);
  if (form.weighting !== defaults?.default_weighting) params.set("wt", form.weighting);
  if (form.rebalance !== DEFAULT_REBALANCE) params.set("reb", form.rebalance);
  if (ticker(form.safeAsset)) params.set("safe", ticker(form.safeAsset));
  if (ticker(form.benchmark)) params.set("b", ticker(form.benchmark));
  writeOverrides(params, SETTINGS_PREFIX, form.settings);
  writeOverrides(params, RANKING_PREFIX, { [form.ranking]: form.rankingParams });
  writeOverrides(params, WEIGHTING_PREFIX, { [form.weighting]: form.weightingParams });
  return params;
}

/** The request without the account, which the page adds from browser storage; null until a universe and an engine are chosen. */
export function rotationBody(form: RotationForm): RotationIn | null {
  const universe = universeBody(form.universe);
  if (!universe || !form.engines.length) return null;
  return {
    ...universe,
    engines: form.engines,
    period: form.period || null,
    ranking: { name: form.ranking, params: form.rankingParams as RuleIn["params"] },
    weighting: { name: form.weighting, params: form.weightingParams as RuleIn["params"] },
    rebalance: form.rebalance,
    safe_asset: ticker(form.safeAsset) || null,
    benchmark: ticker(form.benchmark) || null,
    settings: form.settings,
  };
}

/** How many choices, parameters and settings differ from the defaults; the universe and the engines do not count. */
export const rotationChanges = (form: RotationForm, defaults: RotationDefaults): number =>
  Number(form.period !== "") +
  Number(form.ranking !== defaults.default_ranking) +
  Object.keys(form.rankingParams).length +
  Number(form.weighting !== defaults.default_weighting) +
  Object.keys(form.weightingParams).length +
  Number(form.rebalance !== DEFAULT_REBALANCE) +
  Number(ticker(form.safeAsset) !== "") +
  Number(ticker(form.benchmark) !== "") +
  countChanges(form.settings);

/** True while the universe or an engine is missing, a rule is unknown, a value is invalid or the history is not one the
 * form offers. */
export function hasRotationProblems(form: RotationForm, config: ConfigOut): boolean {
  const ranking = findRule(config.ranking_rules, form.ranking);
  const weighting = findRule(config.weight_rules, form.weighting);
  const tickers = [form.safeAsset, form.benchmark].filter((value) => value.trim() !== "");
  return (
    !rotationBody(form) ||
    !ranking ||
    !weighting ||
    (form.period !== "" && !PERIODS.includes(form.period)) ||
    tickers.some((value) => tickerList(value).length !== 1) ||
    hasProblems({ [ranking.name]: form.rankingParams }, { [ranking.name]: ranking.params }) ||
    hasProblems({ [weighting.name]: form.weightingParams }, { [weighting.name]: weighting.params }) ||
    hasProblems(form.settings, sectionSpecs(pickSections(config.sections, ROTATION_PAGE_SECTIONS)))
  );
}

/** The form with everything but the universe and the engines back at its defaults. */
export const resetRotation = (form: RotationForm, defaults: RotationDefaults): RotationForm => ({
  universe: form.universe,
  engines: form.engines,
  period: "",
  ranking: defaults.default_ranking,
  rankingParams: {},
  weighting: defaults.default_weighting,
  weightingParams: {},
  rebalance: DEFAULT_REBALANCE,
  safeAsset: "",
  benchmark: "",
  settings: {},
});
