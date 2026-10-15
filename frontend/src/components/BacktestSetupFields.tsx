/** The fields of a backtest setup: ticker, signal and its parameters, trade rules and costs. Shared by Backtest and Sweep. */
import { useMemo } from "react";

import type { ConfigOut, SignalOut } from "../api/client";
import { BACKTEST_FIELDS, BACKTEST_SECTIONS, PERIODS } from "../lib/choices";
import { describeSignal, pickSections, type Overrides } from "../lib/overrides";
import type { BacktestSetup } from "../lib/params";
import { ParamFields, SectionFields } from "./ParamFields";
import { FAMILY_LABELS } from "./SignalChip";
import { EntryFields, ExitFields, GroupHeading } from "./TradeRuleFields";
import { Field, Input, Select } from "./ui";

function SignalSelect({ value, onChange, signals }: { value: string; onChange: (value: string) => void; signals: SignalOut[] }) {
  const groups = useMemo(() => {
    const byFamily = new Map<string, SignalOut[]>();
    for (const signal of signals) byFamily.set(signal.family, [...(byFamily.get(signal.family) ?? []), signal]);
    return [...byFamily.entries()];
  }, [signals]);
  return (
    <Select value={value} onChange={(event) => onChange(event.target.value)} required>
      <option value="" disabled>
        Choose a signal…
      </option>
      {groups.map(([family, items]) => (
        <optgroup key={family} label={FAMILY_LABELS[family as SignalOut["family"]]}>
          {items.map((signal) => (
            <option key={signal.name} value={signal.name} title={signal.description}>
              {signal.name} ({signal.direction})
            </option>
          ))}
        </optgroup>
      ))}
    </Select>
  );
}

export function BacktestSetupFields<T extends BacktestSetup>({
  draft,
  onChange,
  config,
  signals,
}: {
  draft: T;
  onChange: (next: T) => void;
  config: ConfigOut;
  signals: SignalOut[];
}) {
  const set = <K extends keyof T>(key: K, value: T[K]) => onChange({ ...draft, [key]: value });
  const selected = signals.find((signal) => signal.name === draft.signal);
  const sections = pickSections(config.sections, BACKTEST_SECTIONS);
  const [stop, costs] = BACKTEST_SECTIONS.map((name) => sections.find((section) => section.name === name));
  const setSettings = (settings: Overrides) => set("settings", settings);

  return (
    <>
      <div className="grid gap-3 sm:grid-cols-[10rem_minmax(0,1fr)_8rem]">
        <Field label="Ticker">
          <Input value={draft.ticker} placeholder="SPY" required onChange={(event) => set("ticker", event.target.value.toUpperCase())} />
        </Field>
        <Field label="Signal" hint={selected ? describeSignal(selected, draft.signalParams) : undefined}>
          {/* Parameters belong to one signal, so switching signals starts from its defaults. */}
          <SignalSelect value={draft.signal} onChange={(signal) => onChange({ ...draft, signal, signalParams: {} })} signals={signals} />
        </Field>
        <Field label="History">
          <Select value={draft.period} onChange={(event) => set("period", event.target.value)}>
            <option value="">default ({config.backtest_period})</option>
            {PERIODS.map((period) => (
              <option key={period} value={period}>
                {period}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      {selected && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">Signal parameters</h2>
          <ParamFields specs={selected.params} values={draft.signalParams} onChange={(signalParams) => set("signalParams", signalParams)} />
        </section>
      )}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Trade rules</h2>
        <div className="grid gap-x-6 gap-y-4 md:grid-cols-2 lg:grid-cols-3">
          <EntryFields
            rules={config.entry_rules}
            entry={draft.entry}
            params={draft.entryParams}
            onChange={(entry, entryParams) => onChange({ ...draft, entry, entryParams })}
          />
          {stop && (
            <div className="space-y-2">
              <GroupHeading>Initial stop (sizes every trade)</GroupHeading>
              <SectionFields section={stop} overrides={draft.settings} onChange={setSettings} only={BACKTEST_FIELDS.risk} className="grid grid-cols-2 gap-3" />
            </div>
          )}
          <ExitFields
            rules={config.exit_rules}
            exits={draft.exits}
            params={draft.exitParams}
            onChange={(exits, exitParams) => onChange({ ...draft, exits, exitParams })}
          />
        </div>
        {costs && (
          <div className="space-y-2">
            <GroupHeading>Costs, metrics and out-of-sample split</GroupHeading>
            <SectionFields section={costs} overrides={draft.settings} onChange={setSettings} />
          </div>
        )}
      </section>
    </>
  );
}
