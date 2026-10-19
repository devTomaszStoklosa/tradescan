/**
 * Inputs generated from the API's parameter declarations, so every parameter the server knows about
 * can be set here without frontend changes. Empty inputs show the default; only changes are kept.
 */
import { useEffect, useId, useState, type ReactNode } from "react";

import type { ParamSpecOut, SettingsSectionOut } from "../api/client";
import {
  problemOf,
  sameValue,
  withOwner,
  withValue,
  type Overrides,
  type ParamValue,
  type Values,
} from "../lib/overrides";
import { fmtParam } from "../lib/format";
import { Input, NumberInput } from "./ui";
import { omit } from "../lib/records";

const cx = (...classes: (string | false | null | undefined)[]) => classes.filter(Boolean).join(" ");

const labelOf = (spec: ParamSpecOut) => (spec.unit ? `${spec.label} (${spec.unit})` : spec.label);

const prettyKey = (key: string) => key.replaceAll("_", " ");

function ParamField({
  spec,
  inputId,
  changed,
  problem,
  onReset,
  children,
}: {
  spec: ParamSpecOut;
  inputId?: string;
  changed: boolean;
  problem: string | null;
  onReset: () => void;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted" title={spec.help || undefined}>
      <div className="flex min-h-4 items-center justify-between gap-2">
        <label htmlFor={inputId} className={cx("truncate", changed && "text-accent")}>
          {labelOf(spec)}
        </label>
        {changed && (
          <button
            type="button"
            onClick={onReset}
            className="shrink-0 text-accent hover:underline"
            aria-label={`Reset ${spec.label} to default`}
          >
            reset
          </button>
        )}
      </div>
      {children}
      {problem && <span className="font-normal text-down">{problem}</span>}
    </div>
  );
}

function NumberParam({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpecOut;
  value: ParamValue | undefined;
  onChange: (value: ParamValue | null) => void;
}) {
  const id = useId();
  const problem = problemOf(spec, value);
  return (
    <ParamField spec={spec} inputId={id} changed={value !== undefined} problem={problem} onReset={() => onChange(null)}>
      <NumberInput
        id={id}
        value={typeof value === "number" ? value : null}
        min={spec.minimum}
        max={spec.maximum}
        step={String(spec.step)}
        placeholder={fmtParam(spec.default)}
        invalid={problem !== null}
        onChange={onChange}
      />
    </ParamField>
  );
}

const listText = (value: ParamValue | undefined) =>
  typeof value === "number" ? String(value) : Array.isArray(value) ? value.join(", ") : "";

/** Numbers in "2, 3" (null when something is not a number, [] when empty). */
const parseList = (text: string): number[] | null => {
  const items = text
    .split(/[\s,;]+/)
    .filter(Boolean)
    .map(Number);
  return items.every(Number.isFinite) ? items : null;
};

function ListParam({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpecOut;
  value: ParamValue | undefined;
  onChange: (value: ParamValue | null) => void;
}) {
  const id = useId();
  const [text, setText] = useState(listText(value));
  // Follow outside changes (reset, back navigation) without rewriting what is being typed, e.g. "2, ".
  useEffect(() => {
    const typed = parseList(text);
    const effective = value ?? spec.default;
    const current = typeof effective === "number" ? [effective] : effective;
    const typedMatches = typed !== null && (typed.length === 0 ? value === undefined : sameValue(typed, current));
    if (!typedMatches) setText(listText(value));
  }, [value]); // only outside changes of `value` matter, not every keystroke

  const update = (next: string) => {
    setText(next);
    const items = parseList(next);
    if (items === null) return;
    onChange(items.length ? items : null);
  };

  const problem = parseList(text) === null ? "Use numbers separated by commas" : problemOf(spec, value);
  return (
    <ParamField spec={spec} inputId={id} changed={value !== undefined} problem={problem} onReset={() => update("")}>
      <Input
        id={id}
        inputMode="decimal"
        value={text}
        placeholder={listText(spec.default)}
        aria-invalid={problem !== null || undefined}
        className={cx(problem !== null && "ring-2 ring-down/60")}
        onChange={(event) => update(event.target.value)}
      />
    </ParamField>
  );
}

function WeightsParam({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpecOut;
  value: ParamValue | undefined;
  onChange: (value: ParamValue | null) => void;
}) {
  const defaults = spec.default as Record<string, number>;
  const current = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const keys = spec.keys ?? Object.keys(defaults);
  const setKey = (key: string, weight: number | null) => {
    const next = weight === null || weight === defaults[key] ? omit(current, key) : { ...current, [key]: weight };
    onChange(Object.keys(next).length ? next : null);
  };
  return (
    <fieldset className="col-span-full min-w-0">
      <ParamField
        spec={spec}
        changed={value !== undefined}
        problem={problemOf(spec, value)}
        onReset={() => onChange(null)}
      >
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {keys.map((key) => (
            <label key={key} className="flex min-w-0 flex-col gap-1 font-normal">
              <span className={cx("truncate", key in current && "text-accent")}>{prettyKey(key)}</span>
              <NumberInput
                label={`${spec.label}: ${prettyKey(key)}`}
                value={current[key] ?? null}
                min={spec.minimum}
                max={spec.maximum}
                step={String(spec.step)}
                placeholder={String(defaults[key] ?? "")}
                onChange={(weight) => setKey(key, weight)}
              />
            </label>
          ))}
        </div>
      </ParamField>
    </fieldset>
  );
}

const GRID = "grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5";

/** One input per declared parameter. Weights without fixed keys (per-signal weights) are left to the caller. */
export function ParamFields({
  specs,
  values,
  onChange,
  className = GRID,
}: {
  specs: ParamSpecOut[];
  values: Values;
  onChange: (values: Values) => void;
  className?: string;
}) {
  const set = (spec: ParamSpecOut) => (value: ParamValue | null) => onChange(withValue(values, spec, value));
  return (
    <div className={className}>
      {specs.map((spec) => {
        const value = values[spec.name];
        if (spec.kind === "weights")
          return spec.keys ? <WeightsParam key={spec.name} spec={spec} value={value} onChange={set(spec)} /> : null;
        if (spec.kind === "int_list" || spec.kind === "float_list")
          return <ListParam key={spec.name} spec={spec} value={value} onChange={set(spec)} />;
        return <NumberParam key={spec.name} spec={spec} value={value} onChange={set(spec)} />;
      })}
    </div>
  );
}

/** The fields of one settings section, reading and writing that section's entry in `overrides`. */
export function SectionFields({
  section,
  overrides,
  onChange,
  only,
  exclude = [],
  className,
}: {
  section: SettingsSectionOut;
  overrides: Overrides;
  onChange: (overrides: Overrides) => void;
  only?: readonly string[];
  exclude?: readonly string[];
  className?: string;
}) {
  const specs = section.params.filter((spec) => (!only || only.includes(spec.name)) && !exclude.includes(spec.name));
  return (
    <ParamFields
      specs={specs}
      values={overrides[section.name] ?? {}}
      onChange={(values) => onChange(withOwner(overrides, section.name, values))}
      className={className}
    />
  );
}
