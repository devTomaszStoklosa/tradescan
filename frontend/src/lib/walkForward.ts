/**
 * Walk-forward analysis: the form and its URL, and the request.
 *
 * A walk-forward is a sweep (the same setup keys and axes, `ax1=signal.oversold&ax1v=5:20:1`) plus the window
 * scheme (`scheme=anchored`, left out for the default) and the metric each in-sample window picks by
 * (`wm=expectancy_r`, left out for the default). The windows, their in-sample length and the trades a pick needs
 * are the `walk_forward` settings (`set.walk_forward.windows=8`).
 */
import type { ConfigOut, SignalOut, WalkForwardIn, WindowScheme } from "../api/client";
import { WALK_FORWARD_SECTION } from "./choices";
import type { Overrides } from "./overrides";
import { writeBacktestForm } from "./params";
import type { RuleDefaults } from "./rules";
import { resetSetup, setupChanges } from "./setup";
import {
  axisValues,
  combinations,
  readSweepForm,
  sweepBody,
  sweepParams,
  withCombination,
  writeSweepForm,
  type SweepForm,
  type SweepParam,
} from "./sweep";

export interface WalkForwardForm extends SweepForm {
  scheme: WindowScheme;
  /** The metric each in-sample window picks the highest of. */
  metric: string;
}

export type WalkForwardDefaults = RuleDefaults & Pick<ConfigOut, "walk_forward">;

/** The settings without the out-of-sample share: it splits a single backtest, while a walk-forward's windows split the history. */
function withoutOosShare(settings: Overrides): Overrides {
  const { backtest, ...rest } = settings;
  if (!backtest) return settings;
  const { oos_pct: _oosPct, ...kept } = backtest;
  return Object.keys(kept).length ? { ...rest, backtest: kept } : rest;
}

export function readWalkForwardForm(params: URLSearchParams, defaults: WalkForwardDefaults): WalkForwardForm {
  const sweep = readSweepForm(params, defaults);
  const limits = defaults.walk_forward;
  return {
    ...sweep,
    settings: withoutOosShare(sweep.settings),
    scheme: limits.schemes.find((scheme) => scheme === params.get("scheme")) ?? limits.default_scheme,
    metric: limits.metrics.find((metric) => metric === params.get("wm")) ?? limits.default_metric,
  };
}

export function writeWalkForwardForm(form: WalkForwardForm, defaults: WalkForwardDefaults): URLSearchParams {
  const params = writeSweepForm(form, defaults);
  if (form.scheme !== defaults.walk_forward.default_scheme) params.set("scheme", form.scheme);
  if (form.metric !== defaults.walk_forward.default_metric) params.set("wm", form.metric);
  return params;
}

/** The parameters a walk-forward can sweep: a sweep's, without the settings its windows fix (the equity it carries over). */
export function walkForwardParams(form: SweepForm, config: ConfigOut, signals: SignalOut[]): SweepParam[] {
  return sweepParams(form, config, signals, config.walk_forward.fixed);
}

/** The out-of-sample windows the form asks for: its `walk_forward.windows` setting, else the configured one. */
export function windowCount(form: SweepForm, config: ConfigOut): number {
  const value = form.settings[WALK_FORWARD_SECTION]?.windows;
  const spec = config.sections.find((section) => section.name === WALK_FORWARD_SECTION)?.params.find((item) => item.name === "windows");
  return typeof value === "number" ? value : typeof spec?.default === "number" ? spec.default : 0;
}

/** Combinations, in-sample windows (the next one included) and the backtests they make; null while an axis is invalid. */
export function walkForwardRuns(form: SweepForm, params: SweepParam[], config: ConfigOut): { combinations: number; windows: number; runs: number } | null {
  const ranges = form.axes.map((axis) => {
    const param = params.find((item) => item.key === axis.key);
    return param ? axisValues(axis, param.spec, config.sweep) : { values: null, problem: "unknown parameter" };
  });
  const count = combinations(ranges);
  if (count === null) return null;
  const windows = windowCount(form, config) + 1;
  return { combinations: count, windows, runs: count * windows };
}

/** The walk-forward request without the account, which the page adds; null until the setup and every axis are valid and within the caps. */
export function walkForwardBody(form: WalkForwardForm, params: SweepParam[], config: ConfigOut): WalkForwardIn | null {
  const sweep = sweepBody(form, params, config.sweep);
  const runs = walkForwardRuns(form, params, config);
  if (!sweep || !runs || runs.runs > config.walk_forward.max_runs) return null;
  return { ...sweep, scheme: form.scheme, metric: form.metric };
}

/** How many settings, rules, the scheme and the selection metric differ from the defaults. */
export function walkForwardChanges(form: WalkForwardForm, config: ConfigOut): number {
  const limits = config.walk_forward;
  return setupChanges(form, config) + Number(form.scheme !== limits.default_scheme) + Number(form.metric !== limits.default_metric);
}

/** The form with every setting, rule, the scheme and the selection metric back at its default; the axes stay. */
export function resetWalkForward(form: WalkForwardForm, config: ConfigOut): WalkForwardForm {
  return { ...resetSetup(form, config), scheme: config.walk_forward.default_scheme, metric: config.walk_forward.default_metric };
}

/** The Backtest page's URL for the setup with a pick's values; the walk-forward's own settings stay behind. */
export function backtestLink(form: WalkForwardForm, params: SweepParam[], values: number[], config: ConfigOut): URLSearchParams {
  const { [WALK_FORWARD_SECTION]: _windows, ...settings } = form.settings;
  return writeBacktestForm({ ...withCombination({ ...form, settings }, params, values), engines: ["vectorized"] }, config);
}
