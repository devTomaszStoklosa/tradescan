/**
 * The swept parameters of a setup: one or two parameters, each with its From, To and Step. Shared by Sweep and
 * Walk-forward, which both run every combination of their values.
 */
import { useMemo } from "react";

import type { ConfigOut } from "../api/client";
import { axisValues, defaultAxis, type AxisForm, type SweepParam } from "../lib/sweep";
import { formatValue } from "./SweepHeatmap";
import { Button, Field, NumberInput, Select } from "./ui";

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

function ParamSelect({ value, params, used, onChange, label }: { value: string; params: SweepParam[]; used: string[]; onChange: (key: string) => void; label: string }) {
  const groups = useMemo(() => {
    const byGroup = new Map<string, SweepParam[]>();
    for (const param of params) byGroup.set(param.group, [...(byGroup.get(param.group) ?? []), param]);
    return [...byGroup.entries()];
  }, [params]);
  const known = params.some((param) => param.key === value);
  return (
    <Select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      {!known && <option value={value}>{value ? `${value} (not in this setup)` : "Choose a parameter…"}</option>}
      {groups.map(([group, items]) => (
        <optgroup key={group} label={group}>
          {items.map((param) => (
            <option key={param.key} value={param.key} disabled={used.includes(param.key) && param.key !== value}>
              {param.spec.unit ? `${param.spec.label} (${param.spec.unit})` : param.spec.label}
            </option>
          ))}
        </optgroup>
      ))}
    </Select>
  );
}

function AxisFields({
  position,
  axis,
  params,
  used,
  limits,
  onChange,
  onRemove,
}: {
  position: number;
  axis: AxisForm;
  params: SweepParam[];
  used: string[];
  limits: ConfigOut["sweep"];
  onChange: (axis: AxisForm) => void;
  onRemove: () => void;
}) {
  const param = params.find((item) => item.key === axis.key);
  const range = param ? axisValues(axis, param.spec, limits) : null;
  const set = (key: "from" | "to" | "step") => (value: number | null) => onChange({ ...axis, [key]: value });
  const name = `Parameter ${position}`;
  return (
    <div className="grid items-end gap-3 sm:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))_auto]">
      <Field label={name}>
        <ParamSelect
          label={name}
          value={axis.key}
          params={params}
          used={used}
          onChange={(key) => {
            const picked = params.find((item) => item.key === key);
            if (picked) onChange(defaultAxis(picked));
          }}
        />
      </Field>
      <Field label="From">
        <NumberInput label={`${name}: from`} value={axis.from} onChange={set("from")} step={String(param?.spec.step ?? "any")} />
      </Field>
      <Field label="To">
        <NumberInput label={`${name}: to`} value={axis.to} onChange={set("to")} step={String(param?.spec.step ?? "any")} />
      </Field>
      <Field label="Step">
        <NumberInput label={`${name}: step`} value={axis.step} onChange={set("step")} step={String(param?.spec.step ?? "any")} min={0} />
      </Field>
      <Button variant="ghost" onClick={onRemove} aria-label={`Remove parameter ${position}`}>
        Remove
      </Button>
      <p className={`text-xs sm:col-span-5 ${range?.values ? "text-muted" : "text-down"}`}>
        {!param
          ? "This parameter is not part of the setup: choose another."
          : range?.values
            ? `${plural(range.values.length, "value")}: ${range.values.slice(0, 6).map(formatValue).join(", ")}${range.values.length > 6 ? ", …" : ""} (setup: ${formatValue(param.current)})`
            : range?.problem}
      </p>
    </div>
  );
}

/** The axes of a sweep with a button to add one; adding needs a chosen signal (`canAdd`). */
export function SweptParameters({
  axes,
  params,
  limits,
  canAdd,
  onChange,
}: {
  axes: AxisForm[];
  params: SweepParam[];
  limits: ConfigOut["sweep"];
  canAdd: boolean;
  onChange: (axes: AxisForm[]) => void;
}) {
  const used = axes.map((axis) => axis.key);
  const addAxis = () => {
    const next = params.find((param) => !used.includes(param.key));
    if (next) onChange([...axes, defaultAxis(next)]);
  };
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">Swept parameters</h2>
      <p className="text-xs text-muted">
        One or two parameters of the setup above. Ranges start around the setup's value, in the parameter's own steps and limits.
      </p>
      {axes.map((axis, index) => (
        <AxisFields
          key={index}
          position={index + 1}
          axis={axis}
          params={params}
          used={used}
          limits={limits}
          onChange={(next) => onChange(axes.map((item, at) => (at === index ? next : item)))}
          onRemove={() => onChange(axes.filter((_, at) => at !== index))}
        />
      ))}
      {axes.length < limits.max_axes && (
        <Button onClick={addAxis} disabled={!canAdd || used.length >= params.length}>
          {axes.length ? "Add a second parameter" : "Add a parameter"}
        </Button>
      )}
    </section>
  );
}
