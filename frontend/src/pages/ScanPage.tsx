import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";

import type { ConfigOut, HitOut, ScanOut, SignalOut, WatchlistOut } from "../api/client";
import { useConfig, useScan, useSignals, useWatchlists } from "../api/hooks";
import { AdvancedSettings } from "../components/AdvancedSettings";
import { HitsTable, hitKey } from "../components/HitsTable";
import { SectionFields } from "../components/ParamFields";
import { RegimeBanner } from "../components/RegimeBanner";
import { TickerPanel } from "../components/TickerPanel";
import { DirectionPicker, FamilyPicker, UniversePicker } from "../components/UniverseFilters";
import { Button, EmptyState, ErrorBox, Field, Input, Loading, Notice, PageHeader, Panel, Select } from "../components/ui";
import { defaultWatchlist, LARGE_UNIVERSE, PERIODS, universeSize } from "../lib/choices";
import { downloadCsv, type CsvRow } from "../lib/csv";
import { fmtNumber } from "../lib/format";
import { hasProblems, pickSections, sectionSpecs, signalSpecs, visibleSignals, type Overrides } from "../lib/overrides";
import { readScanForm, scanBody, tickerList, writeScanForm, type ScanForm } from "../lib/params";
import { useAccount, withAccount } from "../state/account";

/** Settings sections that shape a scan; `scan` first because its two main fields sit in the form row. */
const SCAN_SECTIONS = ["scan", "risk", "scoring", "trend", "regime"] as const;
const MAIN_FIELDS = ["fresh_bars", "min_score"] as const;

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
  config,
  signals,
  busy,
  onSubmit,
}: {
  initial: ScanForm;
  watchlists: WatchlistOut[];
  config: ConfigOut;
  signals: SignalOut[];
  busy: boolean;
  onSubmit: (form: ScanForm) => void;
}) {
  const [draft, setDraft] = useState(() => withDefaultUniverse(initial, watchlists));
  useEffect(() => setDraft(withDefaultUniverse(initial, watchlists)), [initial, watchlists]);
  const sections = pickSections(config.sections, SCAN_SECTIONS);
  const scanSection = sections.find((section) => section.name === "scan");
  const setSettings = (settings: Overrides) => setDraft({ ...draft, settings });
  const benchmark = watchlists.find((item) => item.name === draft.universe.watchlist)?.benchmark ?? config.benchmark;
  const invalid =
    (!draft.universe.watchlist && tickerList(draft.universe.tickers).length === 0) ||
    hasProblems(draft.settings, sectionSpecs(sections)) ||
    hasProblems(draft.signalParams, signalSpecs(signals));

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
          {scanSection && (
            <SectionFields section={scanSection} overrides={draft.settings} onChange={setSettings} only={MAIN_FIELDS} className="grid w-60 grid-cols-2 gap-3" />
          )}
          <div className="w-32">
            <Field label="History">
              <Select value={draft.period} onChange={(event) => setDraft({ ...draft, period: event.target.value })}>
                <option value="">default ({config.scan_period})</option>
                {PERIODS.map((period) => (
                  <option key={period} value={period}>
                    {period}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="w-32">
            <Field label="Benchmark">
              <Input value={draft.benchmark} placeholder={benchmark} onChange={(event) => setDraft({ ...draft, benchmark: event.target.value.toUpperCase() })} />
            </Field>
          </div>
        </div>
        <div className="flex flex-wrap items-end justify-between gap-x-5 gap-y-3">
          <div className="min-w-0 flex-1">
            <FamilyPicker value={draft.families} onChange={(value) => setDraft({ ...draft, families: value })} families={config.families} />
          </div>
          <Button type="submit" variant="primary" disabled={busy || invalid} className="h-9 px-5">
            {busy ? "Scanning…" : "Scan"}
          </Button>
        </div>
      </Panel>
      <AdvancedSettings
        sections={sections}
        settings={draft.settings}
        onSettingsChange={setSettings}
        exclude={{ scan: MAIN_FIELDS }}
        signals={visibleSignals(signals, draft.families, draft.direction)}
        signalParams={draft.signalParams}
        onSignalParamsChange={(signalParams) => setDraft({ ...draft, signalParams })}
        signalWeights
      />
    </form>
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
  const signals = useSignals();
  const watchlists = useWatchlists();
  const { account } = useAccount();
  const form = useMemo(() => readScanForm(params), [params]);
  const body = useMemo(() => {
    const request = scanBody(form);
    return request ? { ...request, settings: withAccount(form.settings, account) } : null;
  }, [form, account]);
  const scan = useScan(body);
  const [selected, setSelected] = useState<HitOut | null>(null);

  const failed = config.error ?? signals.error ?? watchlists.error;
  if (failed) return <ErrorBox error={failed} onRetry={() => window.location.reload()} />;
  if (!config.data || !signals.data || !watchlists.data) return <Loading message="Connecting to the tradescan server…" />;

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
        config={config.data}
        signals={signals.data}
        busy={scan.isFetching}
        onSubmit={(next) => setParams(writeScanForm(next))}
      />
      {!body && <EmptyState title="Pick a universe and press Scan">The scan downloads daily bars, evaluates 38 signals and ranks the setups.</EmptyState>}
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
      {selected && (
        <TickerPanel hit={selected} settings={form.settings} signalParams={form.signalParams} period={form.period} onClose={() => setSelected(null)} />
      )}
    </>
  );
}
