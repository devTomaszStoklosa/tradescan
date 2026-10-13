import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";

import type { Family, HitOut, ScanOut, WatchlistOut } from "../api/client";
import { useConfig, useScan, useWatchlists } from "../api/hooks";
import { HitsTable, hitKey } from "../components/HitsTable";
import { RegimeBanner } from "../components/RegimeBanner";
import { TickerPanel } from "../components/TickerPanel";
import { DirectionPicker, FamilyPicker, UniversePicker } from "../components/UniverseFilters";
import { Button, EmptyState, ErrorBox, Field, Loading, Notice, NumberInput, PageHeader, Panel } from "../components/ui";
import { defaultWatchlist, LARGE_UNIVERSE, universeSize } from "../lib/choices";
import { downloadCsv, type CsvRow } from "../lib/csv";
import { fmtNumber } from "../lib/format";
import { readScanForm, scanBody, tickerList, writeScanForm, type ScanForm } from "../lib/params";
import { toAccountIn, useAccount } from "../state/account";

function withDefaultUniverse(form: ScanForm, watchlists: WatchlistOut[]): ScanForm {
  if (form.universe.watchlist || form.universe.tickers) return form;
  return { ...form, universe: { watchlist: defaultWatchlist(watchlists), tickers: "" } };
}

function hitsToCsv(hits: HitOut[]): CsvRow[] {
  return hits.map((hit) => ({
    ticker: hit.ticker,
    direction: hit.direction,
    date: hit.date,
    score: hit.score.total,
    signals: hit.fired.map((item) => `${item.name}(${item.bars_ago})`).join(" "),
    close: hit.close,
    change_pct: hit.change_pct,
    daily_trend: hit.daily_trend,
    weekly_trend: hit.weekly_trend,
    rs_percentile: hit.rs_percentile,
    atr_pct: hit.atr_pct,
    entry: hit.risk.entry,
    stop: hit.risk.stop,
    ...Object.fromEntries(hit.risk.targets.map((target, index) => [`target_${index + 1}`, target])),
    size: hit.risk.size,
    risk_amount: hit.risk.risk_amount,
    edge_events: hit.edge?.events,
    edge_win_rate: hit.edge?.win_rate,
    edge_mean_return: hit.edge?.mean_return,
    edge_vs_base: hit.edge?.edge,
  }));
}

function ScanFormPanel({
  initial,
  watchlists,
  families,
  defaults,
  busy,
  onSubmit,
}: {
  initial: ScanForm;
  watchlists: WatchlistOut[];
  families: Family[];
  defaults: { freshBars: number; minScore: number };
  busy: boolean;
  onSubmit: (form: ScanForm) => void;
}) {
  const [draft, setDraft] = useState(() => withDefaultUniverse(initial, watchlists));
  useEffect(() => setDraft(withDefaultUniverse(initial, watchlists)), [initial, watchlists]);
  const invalid = !draft.universe.watchlist && tickerList(draft.universe.tickers).length === 0;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!invalid) onSubmit(draft);
  };

  return (
    <Panel>
      <form onSubmit={submit} className="space-y-3">
        <UniversePicker value={draft.universe} onChange={(universe) => setDraft({ ...draft, universe })} watchlists={watchlists} />
        <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
          <DirectionPicker value={draft.direction} onChange={(direction) => setDraft({ ...draft, direction })} />
          <div className="w-28">
            <Field label="Fresh (bars)">
              <NumberInput
                label="Fresh bars"
                value={draft.freshBars}
                min={1}
                step="1"
                placeholder={String(defaults.freshBars)}
                onChange={(freshBars) => setDraft({ ...draft, freshBars })}
              />
            </Field>
          </div>
          <div className="w-28">
            <Field label="Min score">
              <NumberInput
                label="Minimum score"
                value={draft.minScore}
                step="0.5"
                placeholder={fmtNumber(defaults.minScore, 1)}
                onChange={(minScore) => setDraft({ ...draft, minScore })}
              />
            </Field>
          </div>
          <div className="w-full min-w-0 sm:w-auto sm:flex-1">
            <FamilyPicker value={draft.families} onChange={(value) => setDraft({ ...draft, families: value })} families={families} />
          </div>
          <Button type="submit" variant="primary" disabled={busy || invalid} className="h-9 px-5">
            {busy ? "Scanning…" : "Scan"}
          </Button>
        </div>
      </form>
    </Panel>
  );
}

function ScanResults({
  data,
  refreshing,
  onRefresh,
  onSelect,
  selectedKey,
}: {
  data: ScanOut;
  refreshing: boolean;
  onRefresh: () => void;
  onSelect: (hit: HitOut) => void;
  selectedKey: string | null;
}) {
  return (
    <div className="space-y-3">
      <RegimeBanner regime={data.regime} />
      {data.missing.length > 0 && <Notice>No data for: {data.missing.join(", ")}</Notice>}
      {data.skipped.length > 0 && <Notice>Not enough history, skipped: {data.skipped.join(", ")}</Notice>}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted">
          <span className="font-semibold text-fg">{data.hits.length} setups</span> in {data.universe} · score ≥{" "}
          {fmtNumber(data.min_score, 1)} · fired within {data.fresh_bars} bars · edge after {data.edge_horizon} bars
        </p>
        <div className="flex gap-2">
          <Button onClick={onRefresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
          <Button onClick={() => downloadCsv(`tradescan-${data.universe}.csv`, hitsToCsv(data.hits))} disabled={!data.hits.length}>
            Export CSV
          </Button>
        </div>
      </div>
      {data.hits.length ? (
        <HitsTable hits={data.hits} onSelect={onSelect} selectedKey={selectedKey} />
      ) : (
        <EmptyState title="No setups match these filters">Lower the minimum score, widen the freshness window or pick more families.</EmptyState>
      )}
      <p className="text-xs text-muted">Click a row for the chart, risk plan and the signal's history on that ticker.</p>
    </div>
  );
}

export function ScanPage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const watchlists = useWatchlists();
  const { account } = useAccount();
  const form = useMemo(() => readScanForm(params), [params]);
  const body = useMemo(() => {
    const request = scanBody(form);
    return request ? { ...request, account: toAccountIn(account) } : null;
  }, [form, account]);
  const scan = useScan(body);
  const [selected, setSelected] = useState<HitOut | null>(null);

  if (config.isError || watchlists.isError) return <ErrorBox error={config.error ?? watchlists.error} onRetry={() => window.location.reload()} />;
  if (!config.data || !watchlists.data) return <Loading message="Connecting to the tradescan server…" />;

  const size = universeSize(form.universe, watchlists.data);
  const loadingMessage =
    size > LARGE_UNIVERSE
      ? `Scanning ${size} tickers… The first run downloads every ticker and takes 1–2 minutes; cached runs take about 30 s.`
      : `Downloading prices and scanning ${size} tickers… The first run can take 10–30 s; later runs use the cache.`;

  return (
    <>
      <PageHeader title="Scanner" subtitle="Fresh signals ranked by confluence, with an ATR risk plan and historical edge." />
      <ScanFormPanel
        initial={form}
        watchlists={watchlists.data}
        families={config.data.families}
        defaults={{ freshBars: config.data.scan.fresh_bars, minScore: config.data.scan.min_score }}
        busy={scan.isFetching}
        onSubmit={(next) => setParams(writeScanForm(next))}
      />
      {!body && <EmptyState title="Pick a universe and press Scan">The scan downloads daily bars, evaluates 30 signals and ranks the setups.</EmptyState>}
      {scan.isLoading && <Loading message={loadingMessage} />}
      {scan.isError && <ErrorBox error={scan.error} onRetry={() => scan.refetch()} />}
      {scan.data && (
        <ScanResults
          data={scan.data}
          refreshing={scan.isFetching}
          onRefresh={() => scan.refetch()}
          onSelect={setSelected}
          selectedKey={selected ? hitKey(selected) : null}
        />
      )}
      {selected && <TickerPanel hit={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
