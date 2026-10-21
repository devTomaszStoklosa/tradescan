/**
 * Rotation sweep: one rotation over a range of one or two of its parameters. The form and its URL, the parameters a
 * rotation sweep can change and the request.
 *
 * The URL holds the Rotation page's setup (see `rotation`) without the engines, since sweeps run on the vectorized
 * engine alone, and up to two axes as on the Sweep page: `ax1=ranking.lookback&ax1v=126:252:21`. An axis key is
 * `target[.owner].name`, as the API reports it.
 */
import type { ConfigOut, RotationSweepIn, RotationSweepTarget } from "../api/client";
import { withOwner, withValue } from "./overrides";
import {
  DEFAULT_ENGINES,
  readRotationForm,
  rotationBody,
  writeRotationForm,
  type RotationDefaults,
  type RotationForm,
} from "./rotation";
import { findRule } from "./rules";
import { paramsOf, readAxes, sweptAxes, writeAxes, type AxisForm, type TargetParam } from "./sweep";

/** A rotation setup with the axes to sweep; its engines stay the vectorized engine. */
export interface RotationSweepForm extends RotationForm {
  axes: AxisForm[];
}

/** A parameter a rotation sweep can change, with its value in the setup. */
export type RotationSweepParam = TargetParam<RotationSweepTarget>;

export function readRotationSweepForm(params: URLSearchParams, defaults: RotationDefaults): RotationSweepForm {
  return { ...readRotationForm(params, defaults), engines: [...DEFAULT_ENGINES], axes: readAxes(params) };
}

export function writeRotationSweepForm(form: RotationSweepForm, defaults?: RotationDefaults): URLSearchParams {
  return writeAxes(writeRotationForm({ ...form, engines: [...DEFAULT_ENGINES] }, defaults), form.axes);
}

/**
 * Every single-number parameter of the rotation the form offers: the ranking's, the weighting's, the holdings and
 * absolute momentum, and the costs. The settings in `fixed` are left out: the out-of-sample share, which defines the
 * split.
 */
export function rotationSweepParams(
  form: RotationForm,
  config: ConfigOut,
  fixed: readonly string[] = config.rotation_sweep.fixed,
): RotationSweepParam[] {
  const result: RotationSweepParam[] = [];
  const ranking = findRule(config.ranking_rules, form.ranking);
  if (ranking)
    result.push(...paramsOf("ranking", null, `Ranking: ${ranking.label}`, ranking.params, form.rankingParams));
  const weighting = findRule(config.weight_rules, form.weighting);
  if (weighting)
    result.push(...paramsOf("weighting", null, `Weights: ${weighting.label}`, weighting.params, form.weightingParams));
  for (const name of config.rotation_sweep.sections) {
    const section = config.sections.find((item) => item.name === name);
    if (!section) continue;
    const specs = section.params.filter((spec) => !fixed.includes(`${name}.${spec.name}`));
    result.push(...paramsOf("settings", name, section.label, specs, form.settings[name]));
  }
  return result;
}

/** The rotation sweep request without the account, which the page adds; null until the setup and every axis are
 * valid. */
export function rotationSweepBody(
  form: RotationSweepForm,
  params: RotationSweepParam[],
  limits: ConfigOut["rotation_sweep"],
): RotationSweepIn | null {
  const body = rotationBody(form);
  const axes = sweptAxes(form.axes, params, limits);
  if (!body || !axes) return null;
  const { engines: _engines, ...setup } = body;
  return { ...setup, axes };
}

/** The rotation with one combination's values, e.g. to open it on the Rotation page. */
export function withRotationCombination(
  form: RotationForm,
  params: RotationSweepParam[],
  values: number[],
): RotationForm {
  let next = form;
  params.forEach((param, index) => {
    const value = values[index];
    if (value === undefined) return;
    if (param.target === "ranking") next = { ...next, rankingParams: withValue(next.rankingParams, param.spec, value) };
    else if (param.target === "weighting")
      next = { ...next, weightingParams: withValue(next.weightingParams, param.spec, value) };
    else {
      const owner = param.owner ?? "";
      next = {
        ...next,
        settings: withOwner(next.settings, owner, withValue(next.settings[owner] ?? {}, param.spec, value)),
      };
    }
  });
  return next;
}
