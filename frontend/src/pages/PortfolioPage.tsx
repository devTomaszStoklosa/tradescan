import { useMemo, type SubmitEvent } from "react";
import { Link, useSearchParams } from "react-router";

import type {
  ConfigOut,
  PortfolioOut,
  PortfolioPeriodOut,
  PortfolioRunOut,
  SignalOut,
  TickerContributionOut,
  WatchlistOut,
} from "../api/client";
import { useConfig, usePortfolioBacktest, useSignals, useWatchlists } from "../api/hooks";
import { AdvancedSettings } from "../components/AdvancedSettings";
import { enginesAgree, MetricsTable, TradesTable } from "../components/BacktestResults";
import { BacktestSetupFields } from "../components/BacktestSetupFields";
import { EquityChart, type EquityEvent, type EquitySeries } from "../components/charts/EquityChart";
import { DataTable, type Column } from "../components/DataTable";
import { PERIOD_NOTE } from "../components/OutOfSample";
import { SectionFields } from "../components/ParamFields";
import { PinPortfolioRunButton } from "../components/PinRunButton";
import { PortfolioStatsTable } from "../components/PortfolioStats";
import { GroupHeading, RuleChoiceFields } from "../components/TradeRuleFields";
import { UniversePicker } from "../components/UniverseFilters";
import {
  Button,
  DirectionBadge,
  EmptyState,
  ErrorBox,
  Field,
  Loading,
  Notice,
  PageHeader,
  Panel,
  Segmented,
  StatTile,
  ToggleChip,
} from "../components/ui";
import { LARGE_UNIVERSE, PORTFOLIO_SECTION, universeSize, withDefaultUniverse } from "../lib/choices";
import { downloadCsv, tradeRow } from "../lib/csv";
import { DASH, fmtNumber, fmtPct, fmtSigned, tone } from "../lib/format";
import { pickSections } from "../lib/overrides";
import {
  backtestLink,
  choosePriority,
  hasPriorityProblems,
  hasScoreSignalProblems,
  portfolioBody,
  portfolioSections,
  priorityChanges,
  prioritySections,
  readPortfolioForm,
  resetPortfolio,
  scoreExclusions,
  scoreSignals,
  watchlistLink,
  withCountedScoreSignals,
  writePortfolioForm,
  type PortfolioForm,
} from "../lib/portfolio";
import { hasSetupProblems, setupChanges } from "../lib/setup";
import { useResettableState } from "../lib/useResettableState";
import { useAccount, withAccount } from "../state/account";

const ENGINE_COLORS = ["--accent", "--warn"];
/** Above this many tickers, the Cerebro reference takes minutes. */
const SLOW_CEREBRO_TICKERS = 20;

function PortfolioFormPanel({
  initial,
  config,
  signals,
  watchlists,
  busy,
  onSubmit,
}: {
  initial: PortfolioForm;
  config: ConfigOut;
  signals: SignalOut[];
  watchlists: WatchlistOut[];
  busy: boolean;
  onSubmit: (form: PortfolioForm) => void;
}) {
  const source = useMemo(() => withDefaultUniverse(initial, watchlists), [initial, watchlists]);
  const [draft, setDraft] = useResettableState(source);
  const toggleEngine = (engine: string) =>
    setDraft({
      ...draft,
      engines: draft.engines.includes(engine)
        ? draft.engines.filter((item) => item !== engine)
        : [...draft.engines, engine],
    });
  // Score signal parameters left from another traded signal are neither counted nor sent.
  const counted = withCountedScoreSignals(draft, signals);
  const changes = setupChanges(counted, config) + priorityChanges(counted, config);
  const invalid =
    !portfolioBody(counted) ||
    hasSetupProblems(counted, config, signals, portfolioSections(counted, config)) ||
    hasPriorityProblems(counted, config) ||
    hasScoreSignalProblems(counted, signals);
  const watchlistBenchmark = watchlists.find((item) => item.name === draft.universe.watchlist)?.benchmark;
  const portfolio = config.sections.find((section) => section.name === PORTFOLIO_SECTION);
  const slowCerebro =
    draft.engines.includes("cerebro") && universeSize(draft.universe, watchlists) > SLOW_CEREBRO_TICKERS;
  // A priority that scores like the scanner reads the scanner's settings and the parameters and weights of the traded
  // direction's signals; the traded signal's parameters are the setup's.
  const scoreSections = pickSections(config.sections, prioritySections(draft.priority, config));

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (!invalid) onSubmit(counted);
  };

  return (
    <Panel>
      <form onSubmit={submit} noValidate className="space-y-4">
        <UniversePicker
          value={draft.universe}
          onChange={(universe) => setDraft({ ...draft, universe })}
          watchlists={watchlists}
        />
        <BacktestSetupFields
          draft={draft}
          onChange={setDraft}
          config={config}
          signals={signals}
          defaultBenchmark={watchlistBenchmark ?? config.benchmark}
          pyramiding={false}
        />
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Portfolio</h2>
          <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">
            {portfolio && (
              <div className="space-y-2">
                <GroupHeading>Limits (one equity for every ticker)</GroupHeading>
                <SectionFields
                  section={portfolio}
                  overrides={draft.settings}
                  onChange={(settings) => setDraft({ ...draft, settings })}
                  className="grid grid-cols-2 gap-3"
                />
              </div>
            )}
            <RuleChoiceFields
              heading="Priority when more signals fire than fit"
              rules={config.priority_rules}
              value={draft.priority}
              params={draft.priorityParams}
              onChange={(priority, priorityParams) => setDraft(choosePriority(draft, priority, priorityParams, config))}
            />
          </div>
          {scoreSections.length > 0 && (
            <AdvancedSettings
              title="Scan score settings"
              hint="what the scanner's score reads, defaults from settings.toml"
              sections={scoreSections}
              settings={draft.settings}
              onSettingsChange={(settings) => setDraft({ ...draft, settings })}
              exclude={scoreExclusions(scoreSections)}
              signals={scoreSignals(draft, signals)}
              signalParams={counted.scoreSignalParams}
              onSignalParamsChange={(scoreSignalParams) => setDraft({ ...draft, scoreSignalParams })}
              fixedSignals={[draft.signal]}
              signalWeights
            />
          )}
        </section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <Field label="Engines">
            <div className="flex gap-1.5 py-1">
              {config.engines.map((engine) => (
                <ToggleChip
                  key={engine}
                  active={draft.engines.includes(engine)}
                  onClick={() => toggleEngine(engine)}
                  color="var(--accent)"
                >
                  {engine}
                </ToggleChip>
              ))}
            </div>
          </Field>
          <div className="flex items-center gap-2">
            {changes > 0 && (
              <Button variant="ghost" onClick={() => setDraft(resetPortfolio(draft, config))}>
                Reset {changes} changed
              </Button>
            )}
            <Button type="submit" variant="primary" disabled={busy || invalid} className="h-9 px-5">
              {busy ? "Running…" : "Run portfolio"}
            </Button>
          </div>
        </div>
        {slowCerebro && (
          <Notice>
            Cerebro checks the vectorized engine and is slow: expect about a minute per 20 tickers of 10-year history.
          </Notice>
        )}
      </form>
    </Panel>
  );
}

function PortfolioTiles({ period, benchmark }: { period: PortfolioPeriodOut; benchmark: string }) {
  const { metrics: m, stats: s } = period;
  const skipped = s.skipped_no_slot + s.skipped_no_room;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
      <StatTile
        label="Total return"
        value={fmtPct(m.total_return_pct, 1, true)}
        valueClass={tone(m.total_return_pct)}
        sub={`${benchmark} buy & hold ${fmtPct(m.buy_hold_pct, 1, true)}`}
      />
      <StatTile
        label="Max drawdown"
        value={fmtPct(m.max_drawdown_pct, 1)}
        valueClass="text-down"
        sub={`CAGR ${fmtPct(m.cagr_pct, 1, true)}`}
      />
      <StatTile label="Trades" value={String(m.trades)} sub={`win rate ${fmtPct(m.win_rate_pct, 0)}`} />
      <StatTile
        label="Expectancy"
        value={`${fmtSigned(m.expectancy_r)} R`}
        valueClass={tone(m.expectancy_r)}
        sub={`SQN ${fmtNumber(m.sqn)}`}
      />
      <StatTile label="Sharpe" value={fmtNumber(m.sharpe)} sub={`a position on ${fmtPct(m.exposure_pct, 0)} of days`} />
      <StatTile
        label="Open positions"
        value={`${fmtNumber(s.average_positions, 1)} avg`}
        sub={`max ${s.max_positions} · gross exposure ${fmtPct(s.average_exposure_pct, 0)} avg`}
      />
      <StatTile
        label="Skipped signals"
        value={String(skipped)}
        valueClass={skipped ? "text-warn" : undefined}
        sub={`${s.skipped_no_slot} without a slot, ${s.skipped_no_room} without exposure room`}
      />
    </div>
  );
}

const PERIOD_KEYS = [
  { key: "full", label: "Full history" },
  { key: "in_sample", label: "In-sample" },
  { key: "out_of_sample", label: "Out-of-sample" },
] as const;

function PeriodsTables({ run }: { run: PortfolioRunOut }) {
  const periods = useMemo(
    () => PERIOD_KEYS.map(({ key, label }) => ({ key, label, period: key === "full" ? run.full : run[key] })),
    [run],
  );
  const statColumns = useMemo(
    () => periods.map(({ key, label, period }) => ({ key, header: label, stats: period?.stats ?? null })),
    [periods],
  );
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <MetricsTable
        columns={periods.map(({ key, label, period }) => ({ key, header: label, metrics: period?.metrics ?? null }))}
        caption="Portfolio metrics by period"
      />
      <PortfolioStatsTable columns={statColumns} caption="Portfolio stats by period" />
    </div>
  );
}

function ContributionTable({
  run,
  result,
  form,
  config,
}: {
  run: PortfolioRunOut;
  result: PortfolioOut;
  form: PortfolioForm;
  config: ConfigOut;
}) {
  const columns = useMemo<Column<TickerContributionOut>[]>(
    () => [
      {
        key: "ticker",
        header: "Ticker",
        sortValue: (row) => row.ticker,
        render: (row) => (
          <Link
            to={backtestLink(form, row.ticker, run.engine, result.benchmark, config)}
            className="font-mono font-semibold text-accent hover:underline"
            title="Open in Backtest, on its own"
          >
            {row.ticker}
          </Link>
        ),
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
      {
        key: "expectancy",
        header: "Expectancy",
        align: "right",
        sortValue: (row) => row.expectancy_r,
        render: (row) => (
          <span className={tone(row.expectancy_r)}>
            {row.expectancy_r === null ? DASH : `${fmtSigned(row.expectancy_r)} R`}
          </span>
        ),
      },
    ],
    [run, result, form, config],
  );
  return (
    <DataTable
      rows={run.tickers}
      columns={columns}
      rowKey={(row) => row.ticker}
      initialSort={{ key: "pnl", direction: "desc" }}
      caption="Each ticker's contribution"
      dense
    />
  );
}

function PortfolioView({ result, form, config }: { result: PortfolioOut; form: PortfolioForm; config: ConfigOut }) {
  // A new result shows its first engine.
  const [engine, setEngine] = useResettableState(result.runs[0]?.engine ?? "", result);
  const run = result.runs.find((item) => item.engine === engine) ?? result.runs[0];

  const equitySeries = useMemo<EquitySeries[]>(
    () => [
      ...result.runs.map((item, index) => ({
        label: `${item.engine} equity`,
        points: item.equity,
        colorVar: ENGINE_COLORS[index % ENGINE_COLORS.length] ?? "--accent",
        dashed: index > 0,
      })),
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
  const positionSeries = useMemo<EquitySeries[]>(
    () => (run ? [{ label: `open positions (${run.engine})`, points: run.positions, colorVar: "--accent" }] : []),
    [run],
  );
  const splitEvents = useMemo<EquityEvent[]>(
    () => (result.split ? [{ time: result.split.out_of_sample_start, text: "out-of-sample" }] : []),
    [result.split],
  );

  if (!run) return null;
  const used = result.config;
  const exits = result.exits.map((exit) => exit.description).join("; ") || "none, only the stop";
  const filters = result.filters.map((filter) => filter.description).join("; ");
  const agree = enginesAgree(result.runs.map((item) => ({ metrics: item.full.metrics })));
  return (
    <div className="space-y-4">
      <div className="space-y-1 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-lg font-semibold">{result.universe}</span>
          <span className="font-medium">{result.signal}</span>
          <DirectionBadge direction={result.direction} />
          <span className="text-muted">{result.description}</span>
          <div className="ml-auto">
            <PinPortfolioRunButton result={result} engine={run.engine} form={form} />
          </div>
        </div>
        <p className="text-muted">
          {result.start} → {result.end} · {run.tickers.length} tickers, one equity · at most{" "}
          {result.portfolio.max_positions} positions and {fmtNumber(result.portfolio.max_exposure_pct, 0)}% gross
          exposure · priority: {result.priority.description}
        </p>
        <p className="text-muted">
          Risk {fmtNumber(used.risk_pct, 2)}%, max position {fmtNumber(used.max_position_pct, 0)}% · costs{" "}
          {fmtNumber(used.commission_pct, 2)}% + {fmtNumber(used.slippage_pct, 2)}%
        </p>
        {filters && (
          <p className="text-muted">
            Filters: {filters}
            {result.benchmark && ` · benchmark ${result.benchmark}`}
          </p>
        )}
        <p className="text-muted">
          Entry: {result.entry.description} · initial stop {fmtNumber(used.atr_mult, 2)} × ATR({used.atr_period}) ·
          exits: {exits}
        </p>
        <Link to={watchlistLink(form, config)} className="inline-block text-accent hover:underline">
          Each ticker on its own, with its own equity →
        </Link>
      </div>
      {result.missing.length > 0 && <Notice>No data for: {result.missing.join(", ")}</Notice>}
      {result.runs.length > 1 && (
        <div className="flex flex-wrap items-center gap-3">
          <Segmented
            label="Engine"
            value={engine}
            onChange={setEngine}
            options={result.runs.map((item) => ({ value: item.engine, label: item.engine }))}
          />
          <p className={`text-sm ${agree ? "text-up" : "text-warn"}`}>
            {agree ? "✓ Both engines produced identical results." : "Engines differ: compare the trades below."}
          </p>
        </div>
      )}
      <PortfolioTiles period={run.full} benchmark={result.buy_hold_benchmark} />
      <Panel>
        <h2 className="mb-2 text-sm font-semibold">Equity</h2>
        <EquityChart series={equitySeries} events={splitEvents} />
      </Panel>
      <Panel>
        <h2 className="mb-2 text-sm font-semibold">Open positions</h2>
        <EquityChart series={positionSeries} height={140} label="Open positions at each close" />
      </Panel>
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">In-sample and out-of-sample</h2>
        <PeriodsTables run={run} />
        <p className="text-xs text-muted">
          {PERIOD_NOTE} Buy & hold is {result.buy_hold_benchmark}'s; exposure is the share of days with an open
          position.
        </p>
      </section>
      <section className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Each ticker's contribution ({run.engine})</h2>
          <Button
            onClick={() =>
              downloadCsv(
                `tradescan-portfolio-${result.universe}-${result.signal}-tickers.csv`,
                run.tickers.map((row) => ({ ...row })),
              )
            }
          >
            Export CSV
          </Button>
        </div>
        <ContributionTable run={run} result={result} form={form} config={config} />
        <p className="text-xs text-muted">
          Click a ticker to backtest it on its own. Today's index members carry survivorship bias.
        </p>
      </section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">
          {run.trades.length} trades ({run.engine})
        </h2>
        <Button
          onClick={() =>
            downloadCsv(
              `tradescan-portfolio-${result.universe}-${result.signal}-${run.engine}.csv`,
              run.trades.map(tradeRow),
            )
          }
          disabled={!run.trades.length}
        >
          Export CSV
        </Button>
      </div>
      {run.trades.length ? (
        <TradesTable trades={run.trades} />
      ) : (
        <EmptyState title="The signal never triggered a trade in this period" />
      )}
    </div>
  );
}

export function PortfolioPage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const signals = useSignals();
  const watchlists = useWatchlists();
  const { account } = useAccount();
  // The rules a link leaves out are the server's defaults, so the form needs the config first.
  const form = useMemo(() => (config.data ? readPortfolioForm(params, config.data) : null), [params, config.data]);
  const body = useMemo(() => {
    const request = form && portfolioBody(form);
    return form && request ? { ...request, settings: withAccount(form.settings, account) } : null;
  }, [form, account]);
  const run = usePortfolioBacktest(body);

  const failed = config.error ?? signals.error ?? watchlists.error;
  if (failed) return <ErrorBox error={failed} />;
  if (!config.data || !signals.data || !watchlists.data || !form)
    return <Loading message="Connecting to the tradescan server…" />;
  const defaults = config.data;

  return (
    <>
      <PageHeader
        title="Portfolio"
        subtitle="One setup on every ticker of a watchlist with one shared equity: a cap on open positions and on exposure, and a priority when more signals fire than fit."
      />
      <PortfolioFormPanel
        initial={form}
        config={defaults}
        signals={signals.data}
        watchlists={watchlists.data}
        busy={run.isFetching}
        onSubmit={(next) => setParams(writePortfolioForm(next, defaults))}
      />
      {!body && (
        <EmptyState title="Choose a watchlist and a signal">
          Every ticker trades from one account, so the tickers compete for its slots.
        </EmptyState>
      )}
      {run.isLoading && (
        <Loading
          message={
            universeSize(form.universe, watchlists.data) > LARGE_UNIVERSE
              ? "Backtesting a large universe as one portfolio… The first run downloads every ticker and takes 1–2 minutes; cached runs take about a minute."
              : "Downloading history and backtesting the portfolio…"
          }
        />
      )}
      {run.isError && <ErrorBox error={run.error} onRetry={() => void run.refetch()} />}
      {run.data && <PortfolioView result={run.data} form={form} config={defaults} />}
    </>
  );
}
