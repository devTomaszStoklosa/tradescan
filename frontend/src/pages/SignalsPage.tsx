import { useMemo, useState } from "react";

import type { Family, SignalOut } from "../api/client";
import { useConfig, useSignals } from "../api/hooks";
import { DataTable, type Column } from "../components/DataTable";
import { FAMILY_LABELS, SignalChip } from "../components/SignalChip";
import { FamilyPicker } from "../components/UniverseFilters";
import { DirectionBadge, ErrorBox, Field, Input, Loading, PageHeader, Panel } from "../components/ui";
import { fmtNumber, fmtParam } from "../lib/format";

const columns: Column<SignalOut>[] = [
  {
    key: "name",
    header: "Signal",
    sortValue: (s) => s.name,
    render: (s) => <SignalChip name={s.name} family={s.family} />,
  },
  { key: "family", header: "Family", sortValue: (s) => s.family, render: (s) => FAMILY_LABELS[s.family] },
  {
    key: "dir",
    header: "Dir",
    sortValue: (s) => s.direction,
    render: (s) => <DirectionBadge direction={s.direction} />,
  },
  {
    key: "weight",
    header: "Weight",
    title: "Contribution to the scan score (settings.toml)",
    align: "right",
    sortValue: (s) => s.weight,
    render: (s) => fmtNumber(s.weight, 1),
  },
  { key: "description", header: "Rule", className: "min-w-64 text-muted", wrap: true, render: (s) => s.description },
  {
    key: "params",
    header: "Parameters",
    title: "Default value and allowed range; change them per run on the Scanner, Edge and Backtest pages",
    className: "min-w-56 text-xs text-muted",
    wrap: true,
    render: (s) => (
      <ul>
        {s.params.map((spec) => (
          <li key={spec.name} title={spec.help || undefined}>
            {spec.label}: <span className="num text-fg">{fmtParam(spec.default)}</span>
            {spec.unit && ` ${spec.unit}`}{" "}
            <span className="num">
              ({spec.minimum}–{spec.maximum})
            </span>
          </li>
        ))}
      </ul>
    ),
  },
];

export function SignalsPage() {
  const signals = useSignals();
  const config = useConfig();
  const [query, setQuery] = useState("");
  const [families, setFamilies] = useState<Family[]>([]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (signals.data ?? []).filter(
      (signal) =>
        (!families.length || families.includes(signal.family)) &&
        (!needle || signal.name.includes(needle) || signal.description.toLowerCase().includes(needle)),
    );
  }, [signals.data, query, families]);

  if (signals.isError) return <ErrorBox error={signals.error} onRetry={() => void signals.refetch()} />;
  if (!signals.data || !config.data) return <Loading message="Loading signals…" />;

  return (
    <>
      <PageHeader
        title="Signals"
        subtitle="Every rule is evaluated on the bar's close; only the first bar of each run counts as an event."
      />
      <Panel className="flex flex-wrap items-end gap-4">
        <div className="w-64 max-w-full">
          <Field label="Search">
            <Input
              type="search"
              value={query}
              placeholder="breakout, RSI, volume…"
              onChange={(event) => setQuery(event.target.value)}
            />
          </Field>
        </div>
        <FamilyPicker value={families} onChange={setFamilies} families={config.data.families} />
      </Panel>
      <DataTable
        rows={visible}
        columns={columns}
        rowKey={(signal) => signal.name}
        initialSort={{ key: "family", direction: "asc" }}
        caption="Signals"
      />
    </>
  );
}
