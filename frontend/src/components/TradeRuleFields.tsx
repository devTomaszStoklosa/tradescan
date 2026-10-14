/** Entry and exit rule pickers with the chosen rules' parameters, built from the API's rule declarations. */
import { useId } from "react";

import type { RuleOut } from "../api/client";
import { pickOwners, withOwner, type Overrides, type Values } from "../lib/overrides";
import { describeRule, findRule, toggleExit } from "../lib/rules";
import { ParamFields } from "./ParamFields";
import { Select, ToggleChip } from "./ui";

const FIELDS = "grid grid-cols-2 gap-3";

/** Heading of one group of trade rule fields. */
export function GroupHeading({ id, children }: { id?: string; children: string }) {
  return (
    <h3 id={id} className="text-xs font-medium text-muted">
      {children}
    </h3>
  );
}

export function EntryFields({
  rules,
  entry,
  params,
  onChange,
}: {
  rules: RuleOut[];
  entry: string;
  params: Values;
  onChange: (entry: string, params: Values) => void;
}) {
  const id = useId();
  const selected = findRule(rules, entry);
  return (
    <div className="space-y-2">
      <GroupHeading id={id}>Entry</GroupHeading>
      {/* Parameters belong to one rule, so switching rules starts from its defaults. */}
      <Select aria-labelledby={id} value={entry} onChange={(event) => onChange(event.target.value, {})}>
        {!selected && <option value={entry}>{entry} (unknown)</option>}
        {rules.map((rule) => (
          <option key={rule.name} value={rule.name}>
            {rule.label}
          </option>
        ))}
      </Select>
      {selected && (
        <>
          <p className="text-xs text-muted">{describeRule(selected, params)}</p>
          {selected.params.length > 0 && <ParamFields specs={selected.params} values={params} onChange={(next) => onChange(entry, next)} className={FIELDS} />}
        </>
      )}
    </div>
  );
}

export function ExitFields({
  rules,
  exits,
  params,
  onChange,
}: {
  rules: RuleOut[];
  exits: string[];
  /** Parameters by exit rule name. */
  params: Overrides;
  onChange: (exits: string[], params: Overrides) => void;
}) {
  const id = useId();
  const selected = exits.flatMap((name) => findRule(rules, name) ?? []);
  // A rule switched off forgets its changed parameters, so switching it on again starts from the defaults.
  const toggle = (name: string) => {
    const next = toggleExit(exits, name, rules);
    onChange(next, pickOwners(params, next));
  };
  return (
    <div className="space-y-2">
      <GroupHeading id={id}>Exits</GroupHeading>
      <div role="group" aria-labelledby={id} className="flex flex-wrap gap-1.5 py-1">
        {rules.map((rule) => (
          <ToggleChip key={rule.name} active={exits.includes(rule.name)} onClick={() => toggle(rule.name)} color="var(--accent)">
            {rule.label}
          </ToggleChip>
        ))}
      </div>
      {selected.length ? (
        selected.map((rule) => (
          <div key={rule.name} className="space-y-1.5">
            <p className="text-xs text-muted">
              <span className="font-medium text-fg">{rule.label}:</span> {describeRule(rule, params[rule.name])}
            </p>
            {rule.params.length > 0 && (
              <ParamFields
                specs={rule.params}
                values={params[rule.name] ?? {}}
                onChange={(values) => onChange(exits, withOwner(params, rule.name, values))}
                className={FIELDS}
              />
            )}
          </div>
        ))
      ) : (
        <p className="text-xs text-muted">No exit rules: only the initial stop closes a trade.</p>
      )}
    </div>
  );
}
