import { useEffect, useMemo, useState, type SubmitEvent } from "react";
import { useSearchParams } from "react-router";

import type { ConfigOut, PickOut, RotationOut, TickerContributionOut, WatchlistOut } from "../api/client";
import { useConfig, useRotationBacktest, useWatchlists } from "../api/hooks";
import { MetricsTable, TradesTable } from "../components/BacktestResults";
import { EquityChart, type EquityEvent, type EquitySeries } from "../components/charts/EquityChart";
import { DataTable, type Column } from "../components/DataTable";
import { SectionFields } from "../components/ParamFields";
import { RotationStatsTable } from "../components/RotationStats";
import { GroupHeading, RuleChoiceFields } from "../components/TradeRuleFields";
import { UniversePicker } from "../components/UniverseFilters";
import {
  Button,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  Notice,
  PageHeader,
  Panel,
  Segmented,
  Select,
  StatTile,
} from "../components/ui";
import { defaultWatchlist, LARGE_UNIVERSE, PERIODS, ROTATION_SECTION, universeSize } from "../lib/choices";
import { downloadCsv, tradeRow } from "../lib/csv";
import { DASH, fmtNumber, fmtPct, fmtSigned, fmtSize, tone } from "../lib/format";
import {
  hasRotationProblems,
  readRotationForm,
  resetRotation,
  rotationBody,
  rotationChanges,
  writeRotationForm,
  type RotationForm,
} from "../lib/rotation";
import { useAccount, withAccount } from "../state/account";

const REBALANCES = [
  { value: "weekly" as const, label: "Weekly" },
  { value: "monthly" as const, label: "Monthly" },
];

function RotationFormPanel({
  initial,
  config,
  watchlists,
  busy,
  onSubmit,
}: {
  initial: RotationForm;
  config: ConfigOut;
  watchlists: WatchlistOut[];
  busy: boolean;
  onSubmit: (form: RotationForm) => void;
}) {
  const withUniverse = (form: RotationForm): RotationForm =>
    form.universe.watchlist || form.universe.tickers
      ? form
      : { ...form, universe: { watchlist: defaultWatchlist(watchlists), tickers: "" } };
  const [draft, setDraft] = useState(() => withUniverse(initial));
  useEffect(() => setDraft(withUniverse(initial)), [initial, watchlists]);
  const set = <K extends keyof RotationForm>(key: K, value: RotationForm[K]) => setDraft({ ...draft, [key]: value });
  const changes = rotationChanges(draft, config);
  const invalid = hasRotationProblems(draft, config);
  const watchlistBenchmark = watchlists.find((item) => item.name === draft.universe.watchlist)?.benchmark;
  const rotation = config.sections.find((section) => section.name === ROTATION_SECTION);
  const costs = config.sections.find((section) => section.name === "backtest");

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (!invalid) onSubmit(draft);
  };

  return (
    <Panel>
      <form onSubmit={submit} noValidate className="space-y-4">
        <UniversePicker
          value={draft.universe}
          onChange={(universe) => set("universe", universe)}
          watchlists={watchlists}
        />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {/* Not a Field: a label around the buttons would press the first one when its text is clicked. */}
          <div className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted">
            <span>Rebalance</span>
            <Segmented
              label="Rebalance"
              value={draft.rebalance}
              options={REBALANCES}
              onChange={(rebalance) => set("rebalance", rebalance)}
            />
            <span className="font-normal">At the last close of every week or month</span>
          </div>
          <Field label="Safe asset" hint="Takes the slots of picks with negative absolute momentum; empty for cash">
            <Input
              value={draft.safeAsset}
              placeholder="cash, e.g. TLT"
              onChange={(event) => set("safeAsset", event.target.value.toUpperCase())}
            />
          </Field>
          <Field label="Buy & hold benchmark">
            <Input
              value={draft.benchmark}
              placeholder={watchlistBenchmark ?? config.benchmark}
              onChange={(event) => set("benchmark", event.target.value.toUpperCase())}
            />
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
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Picks</h2>
          <div className="grid gap-x-6 gap-y-4 md:grid-cols-2 lg:grid-cols-3">
            <RuleChoiceFields
              heading="Ranking (strongest first)"
              rules={config.ranking_rules}
              value={draft.ranking}
              params={draft.rankingParams}
              onChange={(ranking, rankingParams) => setDraft({ ...draft, ranking, rankingParams })}
            />
            {rotation && (
              <div className="space-y-2">
                <GroupHeading>Holdings and absolute momentum</GroupHeading>
                <SectionFields
                  section={rotation}
                  overrides={draft.settings}
                  onChange={(settings) => set("settings", settings)}
                  className="grid grid-cols-2 gap-3"
                />
              </div>
            )}
            <RuleChoiceFields
              heading="Weights"
              rules={config.weight_rules}
              value={draft.weighting}
              params={draft.weightingParams}
              onChange={(weighting, weightingParams) => setDraft({ ...draft, weighting, weightingParams })}
            />
          </div>
          {costs && (
            <div className="space-y-2">
              <GroupHeading>Costs, metrics and out-of-sample split</GroupHeading>
              <SectionFields
                section={costs}
                overrides={draft.settings}
                onChange={(settings) => set("settings", settings)}
              />
            </div>
          )}
        </section>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {changes > 0 && (
            <Button variant="ghost" onClick={() => setDraft(resetRotation(draft, config))}>
              Reset {changes} changed
            </Button>
          )}
          <Button type="submit" variant="primary" disabled={busy || invalid} className="h-9 px-5">
            {busy ? "Running…" : "Run rotation"}
          </Button>
        </div>
      </form>
    </Panel>
  );
}

function RotationTiles({ result }: { result: RotationOut }) {
  const { metrics: m, stats: s } = result.full;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      <StatTile
        label="Total return"
        value={fmtPct(m.total_return_pct, 1, true)}
        valueClass={tone(m.total_return_pct)}
        sub={`${result.buy_hold_benchmark} buy & hold ${fmtPct(m.buy_hold_pct, 1, true)}`}
      />
      <StatTile
        label="Max drawdown"
        value={fmtPct(m.max_drawdown_pct, 1)}
        valueClass="text-down"
        sub={`CAGR ${fmtPct(m.cagr_pct, 1, true)}`}
      />
      <StatTile label="Sharpe" value={fmtNumber(m.sharpe)} sub={`Sortino ${fmtNumber(m.sortino)}`} />
      <StatTile
        label="Holdings"
        value={`${fmtNumber(s.average_holdings, 1)} avg`}
        sub={`${m.trades} closed, win rate ${fmtPct(m.win_rate_pct, 0)}`}
      />
      <StatTile
        label="Defensive"
        value={fmtPct((s.average_safe_pct ?? 0) + (s.average_cash_pct ?? 0), 0)}
        sub={`${fmtPct(s.average_safe_pct, 0)} safe asset, ${fmtPct(s.average_cash_pct, 0)} cash`}
      />
      <StatTile
        label="Turnover"
        value={`${fmtPct(s.turnover_pct, 0)} / year`}
        sub={`${s.rebalances} rebalances, costs ${fmtNumber(s.commissions, 0)}`}
      />
    </div>
  );
}

const PERIOD_KEYS = [
  { key: "full", label: "Full run" },
  { key: "in_sample", label: "In-sample" },
  { key: "out_of_sample", label: "Out-of-sample" },
] as const;

function PeriodsTables({ result }: { result: RotationOut }) {
  const periods = PERIOD_KEYS.map(({ key, label }) => ({ key, label, period: result[key] }));
  const statColumns = useMemo(
    () => periods.map(({ key, label, period }) => ({ key, header: label, stats: period?.stats ?? null })),
    [result],
  );
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <MetricsTable
        columns={periods.map(({ key, label, period }) => ({ key, header: label, metrics: period?.metrics ?? null }))}
        caption="Rotation metrics by period"
      />
      <RotationStatsTable columns={statColumns} caption="Rotation stats by period" />
    </div>
  );
}

function TargetsTable({ result }: { result: RotationOut }) {
  const defensive = result.rotation.safe_asset ?? "cash";
  const columns = useMemo<Column<PickOut>[]>(
    () => [
      {
        key: "ticker",
        header: "Ticker",
        render: (row) => <span className="font-mono font-semibold">{row.ticker}</span>,
      },
      { key: "score", header: "Score", align: "right", render: (row) => fmtNumber(row.score, 3) },
      {
        key: "momentum",
        header: "Absolute momentum",
        title: `Return over ${result.rotation.absolute_lookback} bars`,
        align: "right",
        render: (row) =>
          row.momentum_pct === null ? (
            DASH
          ) : (
            <span className={tone(row.momentum_pct)}>{fmtPct(row.momentum_pct, 1, true)}</span>
          ),
      },
      { key: "weight", header: "Weight", align: "right", render: (row) => fmtPct(row.weight_pct, 1) },
      {
        key: "held",
        header: "Held",
        render: (row) => (row.held ? "yes" : <span className="text-warn">no, its slot goes to {defensive}</span>),
      },
    ],
    [result, defensive],
  );
  const { targets } = result;
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold">A rebalance at the {targets.date} close would pick</h2>
      {targets.picks.length ? (
        <DataTable rows={targets.picks} columns={columns} rowKey={(row) => row.ticker} caption="Picks by rank" dense />
      ) : (
        <EmptyState title="No ticker can be picked at the last close" />
      )}
      <p className="text-xs text-muted">
        {result.rotation.safe_asset && `${fmtPct(targets.safe_pct, 1)} in ${result.rotation.safe_asset}, `}
        {fmtPct(targets.cash_pct, 1)} in cash. The trades still open are what the rotation holds since its last
        rebalance.
      </p>
    </section>
  );
}

function ContributionTable({ result }: { result: RotationOut }) {
  const columns = useMemo<Column<TickerContributionOut>[]>(
    () => [
      {
        key: "ticker",
        header: "Ticker",
        sortValue: (row) => row.ticker,
        render: (row) => <span className="font-mono font-semibold">{row.ticker}</span>,
      },
      {
        key: "trades",
        header: "Trades",
        align: "right",
        sortValue: (row) => row.trades,
        render: (row) => String(row.trades),
      },
      {
        key: "pnl",
        header: "P&L",
        align: "right",
        sortValue: (row) => row.pnl,
        render: (row) => <span className={tone(row.pnl)}>{fmtSigned(row.pnl, 0)}</span>,
      },
      {
        key: "contribution",
        header: "Contribution",
        title: "P&L in % of the initial equity",
        align: "right",
        sortValue: (row) => row.contribution_pct,
        render: (row) => <span className={tone(row.contribution_pct)}>{fmtPct(row.contribution_pct, 2, true)}</span>,
      },
      {
        key: "win",
        header: "Win rate",
        align: "right",
        sortValue: (row) => row.win_rate_pct,
        render: (row) => fmtPct(row.win_rate_pct, 0),
      },
    ],
    [],
  );
  return (
    <DataTable
      rows={result.tickers}
      columns={columns}
      rowKey={(row) => row.ticker}
      initialSort={{ key: "pnl", direction: "desc" }}
      caption="Each ticker's contribution"
      dense
    />
  );
}

function RotationView({ result }: { result: RotationOut }) {
  const equitySeries = useMemo<EquitySeries[]>(
    () => [
      { label: "rotation equity", points: result.equity, colorVar: "--accent" },
      {
        label: `${result.buy_hold_benchmark} buy & hold`,
        points: result.buy_hold,
        colorVar: "--chart-benchmark",
        dashed: true,
        axis: "left",
      },
    ],
    [result],
  );
  const holdingSeries = useMemo<EquitySeries[]>(
    () => [{ label: "holdings", points: result.holdings, colorVar: "--accent" }],
    [result],
  );
  const splitEvents = useMemo<EquityEvent[]>(
    () => (result.split ? [{ time: result.split.out_of_sample_start, text: "out-of-sample" }] : []),
    [result.split],
  );
  const used = result.config;
  const rotation = result.rotation;
  const check = rotation.absolute_lookback
    ? `a pick at or below 0 over ${rotation.absolute_lookback} bars goes to ${rotation.safe_asset ?? "cash"}`
    : "no absolute momentum check";
  const file = `tradescan-rotation-${result.universe}-${result.ranking.name}`;
  return (
    <div className="space-y-4">
      <div className="space-y-1 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-lg font-semibold">{result.universe}</span>
          <span className="font-medium">
            top {rotation.holdings}, rebalanced {rotation.rebalance}
          </span>
        </div>
        <p className="text-muted">
          {result.start} → {result.end} (from the first rebalance with a pick) · {result.tickers.length} tickers, one
          equity · {check}
        </p>
        <p className="text-muted">
          Ranking: {result.ranking.description} · weights: {result.weighting.description}
        </p>
        <p className="text-muted">
          Costs {fmtNumber(used.commission_pct, 2)}% + {fmtNumber(used.slippage_pct, 2)}% · lot size{" "}
          {fmtSize(used.lot_size)}
        </p>
      </div>
      {result.missing.length > 0 && <Notice>No data for: {result.missing.join(", ")}</Notice>}
      <RotationTiles result={result} />
      <Panel>
        <h2 className="mb-2 text-sm font-semibold">Equity</h2>
        <EquityChart series={equitySeries} events={splitEvents} />
      </Panel>
      <Panel>
        <h2 className="mb-2 text-sm font-semibold">Holdings</h2>
        <EquityChart series={holdingSeries} height={140} label="Tickers held at each close, the safe asset included" />
      </Panel>
      <TargetsTable result={result} />
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">In-sample and out-of-sample</h2>
        <PeriodsTables result={result} />
        <p className="text-xs text-muted">
          Each period starts with fresh equity; the out-of-sample run rebalances from the split on, with its lookbacks
          already warm. Buy & hold is {result.buy_hold_benchmark}'s; exposure is the share of days with a holding. A
          holding has no stop, so it has no R multiple.
        </p>
      </section>
      <section className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Each ticker's contribution</h2>
          <Button
            onClick={() =>
              downloadCsv(
                `${file}-tickers.csv`,
                result.tickers.map((row) => ({ ...row })),
              )
            }
          >
            Export CSV
          </Button>
        </div>
        <ContributionTable result={result} />
        <p className="text-xs text-muted">Today's index members carry survivorship bias.</p>
      </section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{result.trades.length} holdings</h2>
        <Button
          onClick={() => downloadCsv(`${file}.csv`, result.trades.map(tradeRow))}
          disabled={!result.trades.length}
        >
          Export CSV
        </Button>
      </div>
      <p className="text-xs text-muted">
        A holding runs from the buy that opens a position to the sale that empties it; its prices are averages of every
        add and trim.
      </p>
      {result.trades.length ? (
        <TradesTable trades={result.trades} />
      ) : (
        <EmptyState title="The rotation never bought anything" />
      )}
    </div>
  );
}

export function RotationPage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const watchlists = useWatchlists();
  const { account } = useAccount();
  // The rules a link leaves out are the server's defaults, so the form needs the config first.
  const form = useMemo(() => (config.data ? readRotationForm(params, config.data) : null), [params, config.data]);
  const body = useMemo(() => {
    const request = form && rotationBody(form);
    return form && request ? { ...request, settings: withAccount(form.settings, account) } : null;
  }, [form, account]);
  const run = useRotationBacktest(body);

  const failed = config.error ?? watchlists.error;
  if (failed) return <ErrorBox error={failed} />;
  if (!config.data || !watchlists.data || !form) return <Loading message="Connecting to the tradescan server…" />;
  const defaults = config.data;

  return (
    <>
      <PageHeader
        title="Rotation"
        subtitle="Hold the strongest tickers of a watchlist by momentum, rebalanced weekly or monthly, with the slots of falling picks in a safe asset or cash."
      />
      <RotationFormPanel
        initial={form}
        config={defaults}
        watchlists={watchlists.data}
        busy={run.isFetching}
        onSubmit={(next) => setParams(writeRotationForm(next, defaults))}
      />
      {!body && (
        <EmptyState title="Choose a watchlist">The rotation ranks every ticker of it at each rebalance.</EmptyState>
      )}
      {run.isLoading && (
        <Loading
          message={
            universeSize(form.universe, watchlists.data) > LARGE_UNIVERSE
              ? "Ranking a large universe… The first run downloads every ticker and takes 1–2 minutes."
              : "Downloading history and running the rotation…"
          }
        />
      )}
      {run.isError && <ErrorBox error={run.error} onRetry={() => void run.refetch()} />}
      {run.data && <RotationView result={run.data} />}
    </>
  );
}
