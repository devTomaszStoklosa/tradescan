/**
 * The settings a pinned run used, as overrides of the settings sections its page reads.
 *
 * A pin's form keeps only the settings that differed from the defaults when it was pinned, and the defaults are the
 * current settings.toml. Reopening such a form after settings.toml changed would run a different setup, so a reopened
 * run takes every setting from what the pin recorded instead.
 */
import { MONTE_CARLO_SECTION, PORTFOLIO_SECTION, PYRAMID_SECTION, ROTATION_SECTION } from "./choices";
import { MONTE_CARLO_SETTINGS } from "./monteCarlo";
import { withOwner, type Overrides, type ParamValue, type Values } from "./overrides";
import type { PinnedRun, RunConfig, RunKind } from "./runs";

/** The values of `source` named by `names`, skipping those the pin did not record (older pins). */
function pick<T extends object>(source: T, names: readonly (keyof T & string)[]): Values {
  const values: Partial<Record<string, unknown>> = source;
  const result: Values = {};
  for (const name of names) {
    const value = values[name];
    if (typeof value === "number" || Array.isArray(value)) result[name] = value as ParamValue;
  }
  return result;
}

function from(...sections: [owner: string, values: Values][]): Overrides {
  return sections.reduce<Overrides>((result, [owner, values]) => withOwner(result, owner, values), {});
}

/** The stop, costs and pyramiding every setup run recorded in its config. */
const configSettings = (config: RunConfig): [string, Values][] => [
  ["risk", pick(config, ["atr_period", "atr_mult"])],
  ["backtest", pick(config, ["commission_pct", "slippage_pct", "bars_per_year", "oos_pct"])],
  [PYRAMID_SECTION, pick(config, ["max_units", "add_every_atr"])],
];

/** What only one kind of run recorded; a new kind of run adds its entry here. */
type SettingsSpec<S extends PinnedRun> = (run: S) => Overrides;

type PinnedOf<K extends RunKind> = Extract<PinnedRun, { kind: K }>;

const KINDS: { [K in RunKind]: SettingsSpec<PinnedOf<K>> } = {
  backtest: (run) =>
    from(...configSettings(run.config), [
      MONTE_CARLO_SECTION,
      run.monteCarlo ? pick(run.monteCarlo, MONTE_CARLO_SETTINGS) : {},
    ]),
  // The portfolio backtest has no pyramiding and no Monte Carlo.
  portfolio: (run) =>
    from(...configSettings(run.config).filter(([owner]) => owner !== PYRAMID_SECTION), [
      PORTFOLIO_SECTION,
      pick(run.portfolio, ["max_positions", "max_exposure_pct"]),
    ]),
  rotation: (run) =>
    from(
      ["backtest", pick(run.config, ["commission_pct", "slippage_pct", "bars_per_year", "oos_pct"])],
      [ROTATION_SECTION, pick(run.rotation, ["holdings", "absolute_lookback"])],
    ),
};

/** Every setting of the sections the run's page reads that the pin recorded; the account is not one of them. */
export const pinnedSettings = (run: PinnedRun): Overrides => (KINDS[run.kind] as SettingsSpec<PinnedRun>)(run);

/** The run's form settings with the recorded values on top, so none falls back to today's settings.toml. */
export const reopenedSettings = (run: PinnedRun): Overrides => {
  const recorded = pinnedSettings(run);
  const owners = new Set([...Object.keys(run.form.settings), ...Object.keys(recorded)]);
  return Object.fromEntries([...owners].map((owner) => [owner, { ...run.form.settings[owner], ...recorded[owner] }]));
};
