import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";

import type { EdgeOut, Family, SignalOut, WatchlistOut } from "../api/client";
import { useConfig, useEdge, useSignals, useWatchlists } from "../api/hooks";
import { AdvancedSettings } from "../components/AdvancedSettings";
import { EdgeTable } from "../components/EdgeTable";
import { DirectionPicker, FamilyPicker, UniversePicker } from "../components/UniverseFilters";
import { Button, EmptyState, ErrorBox, Field, Input, Loading, Notice, NumberInput, PageHeader, Panel, Select } from "../components/ui";
import { defaultWatchlist, LARGE_UNIVERSE, PERIODS, universeSize } from "../lib/choices";
import { downloadCsv, type CsvRow } from "../lib/csv";
import { hasProblems, signalSpecs, visibleSignals } from "../lib/overrides";
import { edgeBody, parseHorizons, readEdgeForm, writeEdgeForm, type EdgeForm } from "../lib/params";

function edgeToCsv(data: EdgeOut): CsvRow[] {
  return data.rows.map((row) => ({
    signal: row.signal,
    direction: row.direction,
    family: row.family,
    ...Object.fromEntries(
      row.stats.flatMap((stats) => [
        [`events_${stats.horizon}d`, stats.events],
        [`win_rate_${stats.horizon}d`, stats.win_rate],
        [`mean_return_${stats.horizon}d`, stats.mean_return],
        [`vs_base_${stats.horizon}d`, stats.edge],
      ]),
    ),
  }));
}

function EdgeFormPanel({
  initial,
  watchlists,
  families,
  signals,
  defaultPeriod,
  busy,
  onSubmit,
}: {
  initial: EdgeForm;
  watchlists: WatchlistOut[];
  families: Family[];
  signals: SignalOut[];
  defaultPeriod: string;
  busy: boolean;
  onSubmit: (form: EdgeForm) => void;
}) {
  const withUniverse = (form: EdgeForm): EdgeForm =>
    form.universe.watchlist || form.universe.tickers ? form : { ...form, universe: { watchlist: defaultWatchlist(watchlists), tickers: "" } };
  const [draft, setDraft] = useState(() => withUniverse(initial));
  useEffect(() => setDraft(withUniverse(initial)), [initial, watchlists]);
  const invalid = !edgeBody(draft) || hasProblems(draft.signalParams, signalSpecs(signals));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!invalid) onSubmit(draft);
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-3">
      <Panel className="space-y-3">
        <UniversePicker value={draft.universe} onChange={(universe) => setDraft({ ...draft, universe })} watchlists={watchlists} />
        <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
          <DirectionPicker value={draft.direction} onChange={(direction) => setDraft({ ...draft, direction })} />
          <div className="w-32">
            <Field label="Horizons (bars)">
              <Input value={draft.horizons} onChange={(event) => setDraft({ ...draft, horizons: event.target.value })} placeholder="5,10,20" />
            </Field>
          </div>
          <div className="w-28">
            <Field label="Min events">
              <NumberInput value={draft.minEvents} min={0} step="1" onChange={(value) => setDraft({ ...draft, minEvents: value ?? 0 })} />
            </Field>
          </div>
          <div className="w-36">
            <Field label="History">
              <Select value={draft.period} onChange={(event) => setDraft({ ...draft, period: event.target.value })}>
                <option value="">default ({defaultPeriod})</option>
                {PERIODS.map((period) => (
                  <option key={period} value={period}>
                    {period}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="w-full min-w-0 sm:w-auto sm:flex-1">
            <FamilyPicker value={draft.families} onChange={(value) => setDraft({ ...draft, families: value })} families={families} />
          </div>
          <Button type="submit" variant="primary" disabled={busy || invalid} className="h-9 px-5">
            {busy ? "Computing…" : "Compute edge"}
          </Button>
        </div>
      </Panel>
      <AdvancedSettings
        sections={[]}
        settings={{}}
        onSettingsChange={() => undefined}
        signals={visibleSignals(signals, draft.families, draft.direction)}
        signalParams={draft.signalParams}
        onSignalParamsChange={(signalParams) => setDraft({ ...draft, signalParams })}
      />
    </form>
  );
}

export function EdgePage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const signals = useSignals();
  const watchlists = useWatchlists();
  const form = useMemo(() => readEdgeForm(params), [params]);
  const body = useMemo(() => edgeBody(form), [form]);
  const edge = useEdge(body);

  const failed = config.error ?? signals.error ?? watchlists.error;
  if (failed) return <ErrorBox error={failed} />;
  if (!config.data || !signals.data || !watchlists.data) return <Loading message="Connecting to the tradescan server…" />;

  return (
    <>
      <PageHeader
        title="Signal edge"
        subtitle="What happened after every past signal, pooled across the universe, compared with entering on any bar."
      />
      <EdgeFormPanel
        initial={form}
        watchlists={watchlists.data}
        families={config.data.families}
        signals={signals.data}
        defaultPeriod={config.data.backtest_period}
        busy={edge.isFetching}
        onSubmit={(next) => setParams(writeEdgeForm(next))}
      />
      {!body && <EmptyState title="Pick a universe and press Compute edge" />}
      {edge.isLoading && (
        <Loading
          message={
            universeSize(form.universe, watchlists.data) > LARGE_UNIVERSE
              ? "Evaluating every signal on a large universe… The first run downloads 10 years per ticker and takes 1–2 minutes; cached runs take under a minute."
              : "Downloading long history and evaluating every signal…"
          }
        />
      )}
      {edge.isError && <ErrorBox error={edge.error} onRetry={() => edge.refetch()} />}
      {edge.data && (
        <div className="space-y-3">
          {edge.data.missing.length > 0 && <Notice>No data for: {edge.data.missing.join(", ")}</Notice>}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-muted">
              <span className="font-semibold text-fg">{edge.data.rows.length} signals</span> on {edge.data.universe} ({edge.data.tickers}{" "}
              tickers) · horizons {parseHorizons(form.horizons).join(", ")} bars
            </p>
            <Button onClick={() => downloadCsv(`tradescan-edge-${edge.data.universe}.csv`, edgeToCsv(edge.data))} disabled={!edge.data.rows.length}>
              Export CSV
            </Button>
          </div>
          {edge.data.rows.length ? (
            <EdgeTable rows={edge.data.rows} horizons={edge.data.horizons} minEvents={form.minEvents} />
          ) : (
            <EmptyState title="No signal has enough events">Lower the minimum events or use a longer history.</EmptyState>
          )}
          <p className="text-xs text-muted">
            Returns are in the signal's direction from the next open. Event counts below 20 are highlighted: treat them as noise. Today's
            index members carry survivorship bias.
          </p>
        </div>
      )}
    </>
  );
}
