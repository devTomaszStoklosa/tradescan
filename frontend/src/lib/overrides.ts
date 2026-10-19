/**
 * Per-run parameter overrides, built from the API's parameter declarations.
 *
 * Only values that differ from the default are kept, so URLs stay short and a run is fully described
 * by its link. Owners are settings sections ("risk"), signal names ("connors_rsi2_long") or trade rule names ("limit", "trend").
 */
import type { ParamSpecOut, SettingsSectionOut, SignalOut } from "../api/client";
import { omit } from "./records";

export type ParamValue = number | number[] | Record<string, number>;
/** Changed values of one owner, by parameter name. */
export type Values = Record<string, ParamValue>;
/** Changed values by owner. */
export type Overrides = Record<string, Values>;

/**
 * URL prefixes: `set.risk.atr_mult=3`, `sig.donchian_breakout.period=30`, `set.scoring.family_weights.breakout=2`,
 * and for a backtest's trade rules `en.limit.offset_atr=1`, `ex.target.target_r=3` and `fi.trend.period=100`.
 */
export const SETTINGS_PREFIX = "set";
export const SIGNALS_PREFIX = "sig";
export const ENTRY_PREFIX = "en";
export const EXIT_PREFIX = "ex";
export const FILTER_PREFIX = "fi";

export const EMPTY: Overrides = {};

export function sameValue(left: ParamValue | undefined, right: ParamValue | undefined): boolean {
  if (left === undefined || right === undefined) return left === right;
  if (typeof left === "number" || typeof right === "number") return left === right;
  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((item, index) => item === right[index])
    );
  }
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  return [...keys].every((key) => left[key] === right[key]);
}

/** Set one value (null clears it). A value equal to the default is dropped, so only changes remain. */
export function withValue(values: Values, spec: ParamSpecOut, value: ParamValue | null): Values {
  if (value === null || sameValue(value, spec.default)) return omit(values, spec.name);
  return { ...values, [spec.name]: value };
}

/** Replace one owner's values; owners without changes are removed. */
export function withOwner(overrides: Overrides, owner: string, values: Values): Overrides {
  return Object.keys(values).length ? { ...overrides, [owner]: values } : omit(overrides, owner);
}

export function pickOwners(overrides: Overrides, owners: readonly string[]): Overrides {
  return Object.fromEntries(Object.entries(overrides).filter(([owner]) => owners.includes(owner)));
}

/** Only the listed parameters of the listed owners, e.g. {risk: ["atr_mult"]}. */
export function pickFields(overrides: Overrides, fields: Record<string, readonly string[]>): Overrides {
  let result: Overrides = {};
  for (const [owner, names] of Object.entries(fields)) {
    const values = Object.fromEntries(Object.entries(overrides[owner] ?? {}).filter(([name]) => names.includes(name)));
    result = withOwner(result, owner, values);
  }
  return result;
}

export function countChanges(overrides: Overrides, owners?: readonly string[]): number {
  return Object.entries(overrides)
    .filter(([owner]) => !owners || owners.includes(owner))
    .reduce((total, [, values]) => total + Object.keys(values).length, 0);
}

// --- Validation (the server checks again; this only keeps obviously bad runs from being sent) -------

const describeRange = (spec: ParamSpecOut) => `${spec.minimum}–${spec.maximum}`;

function numberProblem(spec: ParamSpecOut, value: number, whole: boolean): string | null {
  if (!Number.isFinite(value)) return "Enter a number";
  if (whole && !Number.isInteger(value)) return "Enter a whole number";
  if (value < spec.minimum || value > spec.maximum) return `Allowed: ${describeRange(spec)}`;
  return null;
}

export function problemOf(spec: ParamSpecOut, value: ParamValue | undefined): string | null {
  if (value === undefined) return null;
  switch (spec.kind) {
    case "int":
    case "float":
      return typeof value === "number" ? numberProblem(spec, value, spec.kind === "int") : "Enter a number";
    case "int_list":
    case "float_list": {
      const items = typeof value === "number" ? [value] : Array.isArray(value) ? value : null;
      if (!items?.length) return "Enter at least one number";
      for (const item of items) {
        const problem = numberProblem(spec, item, spec.kind === "int_list");
        if (problem) return problem;
      }
      return null;
    }
    case "weights": {
      if (typeof value !== "object" || Array.isArray(value)) return "Enter weights";
      for (const [key, item] of Object.entries(value)) {
        if (spec.keys && !spec.keys.includes(key)) return `Unknown key ${key}`;
        const problem = numberProblem(spec, item, false);
        if (problem) return `${key}: ${problem}`;
      }
      return null;
    }
  }
}

/** Specs by owner: settings sections by name, signals by name. */
export type SpecIndex = Record<string, ParamSpecOut[]>;

/** The named sections, in the given order. */
export const pickSections = (sections: SettingsSectionOut[], names: readonly string[]): SettingsSectionOut[] =>
  names.flatMap((name) => sections.filter((section) => section.name === name));

/** Signals a family/direction filter keeps (no families means all). */
export const visibleSignals = (signals: SignalOut[], families: readonly string[], direction: string): SignalOut[] =>
  signals.filter(
    (signal) =>
      (!families.length || families.includes(signal.family)) &&
      (direction === "both" || signal.direction === direction),
  );

export const sectionSpecs = (sections: SettingsSectionOut[]): SpecIndex =>
  Object.fromEntries(sections.map((section) => [section.name, section.params]));

export const signalSpecs = (signals: SignalOut[]): SpecIndex =>
  Object.fromEntries(signals.map((signal) => [signal.name, signal.params]));

/** True when any override names an unknown parameter or holds an invalid value. */
export function hasProblems(overrides: Overrides, specs: SpecIndex): boolean {
  return Object.entries(overrides).some(([owner, values]) =>
    Object.entries(values).some(([name, value]) => {
      const spec = specs[owner]?.find((item) => item.name === name);
      return !spec || problemOf(spec, value) !== null;
    }),
  );
}

// --- URL ------------------------------------------------------------------------------------------

export function writeOverrides(params: URLSearchParams, prefix: string, overrides: Overrides): void {
  for (const [owner, values] of Object.entries(overrides)) {
    for (const [name, value] of Object.entries(values)) {
      const key = `${prefix}.${owner}.${name}`;
      if (typeof value === "number") params.set(key, String(value));
      else if (Array.isArray(value)) params.set(key, value.join(","));
      else for (const [entry, weight] of Object.entries(value)) params.set(`${key}.${entry}`, String(weight));
    }
  }
}

const toNumber = (text: string): number | null => {
  if (text.trim() === "") return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
};

/** Values the URL cannot express are skipped; the server validates whatever remains. */
export function readOverrides(params: URLSearchParams, prefix: string): Overrides {
  const result: Overrides = {};
  for (const [key, raw] of params) {
    if (!key.startsWith(`${prefix}.`)) continue;
    const parts = key.slice(prefix.length + 1).split(".");
    const [owner, name, entry] = parts;
    if (!owner || !name || parts.length > 3) continue;
    const values: Values = { ...result[owner] };
    if (entry !== undefined) {
      const weight = toNumber(raw);
      const current = values[name];
      const weights = current && typeof current === "object" && !Array.isArray(current) ? current : {};
      if (weight !== null) values[name] = { ...weights, [entry]: weight };
    } else if (raw.includes(",")) {
      const items = raw.split(",").map(toNumber);
      if (items.every((item) => item !== null)) values[name] = items;
    } else {
      const value = toNumber(raw);
      if (value !== null) values[name] = value;
    }
    if (Object.keys(values).length) result[owner] = values;
  }
  return result;
}

// --- Signal descriptions --------------------------------------------------------------------------

const PLACEHOLDER = /\{(\w+)(?::([^}]*))?\}/g;

function formatValue(value: ParamValue | undefined, spec: string): string {
  if (typeof value !== "number") return Array.isArray(value) ? value.join(", ") : "?";
  if (spec === ".0%") return `${Math.round(value * 100)}%`;
  return String(value);
}

/** Fill a server template ("RSI({period}) < {level:g}") with values; mirrors Python's format for "", "g", ".0%". */
export function formatTemplate(template: string, values: Values): string {
  return template.replace(PLACEHOLDER, (_, name: string, spec: string | undefined) =>
    formatValue(values[name], spec ?? ""),
  );
}

/** Anything with declared parameters and a description template: a signal or a trade rule. */
type Described = Pick<SignalOut, "params" | "template">;

export function signalValues(signal: Described, overrides: Values | undefined): Values {
  return { ...Object.fromEntries(signal.params.map((spec) => [spec.name, spec.default])), ...overrides };
}

export const describeSignal = (signal: Described, overrides: Values | undefined): string =>
  formatTemplate(signal.template, signalValues(signal, overrides));
