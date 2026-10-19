/**
 * Comparison of pinned runs: which parameters differ and which run is best on each metric.
 * Labels and units come from the API's parameter specs, so parameters added later appear without frontend changes.
 */
import type { ConfigOut, MetricsOut, ParamSpecOut, Point, SettingsSectionOut, SignalOut } from "../api/client";
import { MONTE_CARLO_SECTION, PORTFOLIO_SECTION } from "./choices";
import { DASH } from "./format";
import { MONTE_CARLO_SETTINGS } from "./monteCarlo";
import type { RuleSpecs } from "./rules";
import { asBacktest, asPortfolio, type PinnedPortfolioRun, type PinnedRun, type RunKind } from "./runs";

/** Fewer trades than this make a run's metrics mostly noise. */
export const MIN_TRADES = 20;

export type MetricKey = Exclude<keyof MetricsOut, "profit_factor_infinite">;

export interface ParamRow {
  key: string;
  label: string;
  unit: string;
  /** Formatted value per run, in the order of the runs given. */
  values: string[];
  differs: boolean;
}

type Raw = number | number[] | Record<string, number> | string | undefined;
type Params = Record<string, number | number[]>;

function humanize(name: string): string {
  const words = name.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function display(value: Raw): string {
  if (value === undefined) return DASH;
  if (typeof value === "number") return value.toLocaleString("en-US", { maximumFractionDigits: 6 });
  if (Array.isArray(value)) return value.map((item) => display(item)).join(", ");
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key} ${display(item)}`).join(", ") || "none";
  return value;
}

function row(key: string, label: string, unit: string, raw: Raw[]): ParamRow {
  const distinct = new Set(raw.map((value) => JSON.stringify(value ?? null)));
  return { key, label, unit, values: raw.map(display), differs: distinct.size > 1 };
}

/** Keys of all records, in first-seen order. */
const keysOf = (records: object[]): string[] => [...new Set(records.flatMap((record) => Object.keys(record)))];

/**
 * Rows for parameters that belong to an owner (a signal or a rule), keyed by owner so two owners' "period"
 * never share a row. `paramsOf` is undefined for runs that do not use the owner.
 */
function ownedRows(
  prefix: string,
  owners: Iterable<string>,
  labelOf: (owner: string) => string,
  specsOf: (owner: string) => ParamSpecOut[],
  paramsOf: (run: PinnedRun, owner: string) => Params | undefined,
  runs: PinnedRun[],
): ParamRow[] {
  const rows: ParamRow[] = [];
  for (const owner of owners) {
    const params = runs.map((run) => paramsOf(run, owner));
    for (const name of keysOf(params.filter((item) => item !== undefined))) {
      const spec = specsOf(owner).find((item) => item.name === name);
      rows.push(row(`${prefix}.${owner}.${name}`, `${labelOf(owner)} · ${spec?.label ?? humanize(name)}`, spec?.unit ?? "", params.map((item) => item?.[name])));
    }
  }
  return rows;
}

/** The rules' specs, with the priority rules when portfolio runs are compared. */
export type CompareSpecs = RuleSpecs & Partial<Pick<ConfigOut, "priority_rules">>;

const KIND_LABELS: Record<RunKind, string> = { backtest: "Backtest", portfolio: "Portfolio" };

/** Each run as a portfolio run, undefined for the others; empty when no run is a portfolio, so no portfolio rows appear. */
function portfolioRuns(runs: PinnedRun[]): (PinnedPortfolioRun | undefined)[] {
  const portfolios = runs.map(asPortfolio);
  return portfolios.some(Boolean) ? portfolios : [];
}

/** What a portfolio run tested: its kind, universe and number of tickers. */
function universeRows(runs: PinnedRun[], portfolios: (PinnedPortfolioRun | undefined)[]): ParamRow[] {
  if (!portfolios.length) return [];
  return [
    row("kind", "Run", "", runs.map((run) => KIND_LABELS[run.kind])),
    row("universe", "Universe", "", portfolios.map((run) => run?.universe)),
    row("tickers", "Tickers", "", portfolios.map((run) => run?.tickers.length)),
  ];
}

/** The max positions and the max exposure of portfolio runs, labelled like the Portfolio page's fields. */
function portfolioSettingRows(portfolios: (PinnedPortfolioRun | undefined)[], sections: SettingsSectionOut[]): ParamRow[] {
  const section = sections.find((item) => item.name === PORTFOLIO_SECTION);
  const settings = portfolios.map((run) => run?.portfolio as Record<string, number> | undefined);
  return keysOf(settings.filter((item) => item !== undefined)).map((name) => {
    const spec = section?.params.find((item) => item.name === name);
    return row(`portfolio.${name}`, `${section?.label ?? "Portfolio"} · ${spec?.label ?? humanize(name)}`, spec?.unit ?? "", settings.map((item) => item?.[name]));
  });
}

/** The rule that ranked a portfolio's signals, with its parameters. */
function priorityRows(runs: PinnedRun[], portfolios: (PinnedPortfolioRun | undefined)[], rules: CompareSpecs): ParamRow[] {
  if (!portfolios.length) return [];
  const labels = new Map(portfolios.flatMap((run) => (run ? [[run.priority.name, run.priority.label] as const] : [])));
  return [
    row("priority", "Priority", "", portfolios.map((run) => run?.priority.label)),
    ...ownedRows(
      "priority",
      labels.keys(),
      (name) => labels.get(name) ?? name,
      (name) => rules.priority_rules?.find((rule) => rule.name === name)?.params ?? [],
      (run, name) => {
        const priority = asPortfolio(run)?.priority;
        return priority?.name === name ? priority.params : undefined;
      },
      runs,
    ),
  ];
}

/**
 * What a portfolio's priority read of the scanner: its settings, labelled like the Portfolio page's fields, and the
 * parameters of the signals the score counted besides the traded one.
 */
function scanRows(
  runs: PinnedRun[],
  portfolios: (PinnedPortfolioRun | undefined)[],
  sections: SettingsSectionOut[],
  signals: SignalOut[],
): ParamRow[] {
  const scans = portfolios.map((run) => run?.scan ?? undefined);
  const present = scans.filter((scan) => scan !== undefined);
  const rows: ParamRow[] = [];
  for (const name of keysOf(present.map((scan) => scan.settings))) {
    const section = sections.find((item) => item.name === name);
    const settings = scans.map((scan) => scan?.settings[name]);
    for (const param of keysOf(settings.filter((item) => item !== undefined))) {
      const spec = section?.params.find((item) => item.name === param);
      const label = `${section?.label ?? humanize(name)} · ${spec?.label ?? humanize(param)}`;
      rows.push(row(`scan.${name}.${param}`, label, spec?.unit ?? "", settings.map((item) => item?.[param])));
    }
  }
  rows.push(
    ...ownedRows(
      "score_params",
      keysOf(present.map((scan) => scan.signal_params)),
      (signal) => `Score · ${signal}`,
      (signal) => signals.find((item) => item.name === signal)?.params ?? [],
      (run, signal) => asPortfolio(run)?.scan?.signal_params[signal],
      runs,
    ),
  );
  return rows;
}

/**
 * Every input of the runs as rows: what was tested (a ticker, or a portfolio's universe), the data range, the stop,
 * costs and account, a portfolio's max positions and max exposure, the Monte Carlo settings, the entry filters
 * (and the benchmark they compared), the entry and exit rules with their parameters, a portfolio's priority rule
 * with its parameters and what it read of the scanner, and the signal parameters.
 */
export function parameterRows(
  runs: PinnedRun[],
  sections: SettingsSectionOut[] = [],
  signals: SignalOut[] = [],
  rules: CompareSpecs = { entry_rules: [], exit_rules: [], filter_rules: [] },
): ParamRow[] {
  const settingSpecs = sections.flatMap((section) => section.params);
  const portfolios = portfolioRuns(runs);
  const rows: ParamRow[] = [
    ...universeRows(runs, portfolios),
    row("ticker", "Ticker", "", runs.map((run) => asBacktest(run)?.ticker)),
    row("signal", "Signal", "", runs.map((run) => run.signal)),
    row("engine", "Engine", "", runs.map((run) => run.engine)),
    row("data", "Data", "", runs.map((run) => `${run.start} → ${run.end}`)),
  ];
  for (const name of keysOf(runs.map((run) => run.config))) {
    const spec = settingSpecs.find((item) => item.name === name);
    const values = runs.map((run) => (run.config as unknown as Record<string, number | undefined>)[name]);
    rows.push(row(`config.${name}`, spec?.label ?? humanize(name), spec?.unit ?? "", values));
  }
  rows.push(...portfolioSettingRows(portfolios, sections));
  if (runs.some((run) => run.monteCarlo)) {
    const section = sections.find((item) => item.name === MONTE_CARLO_SECTION);
    for (const name of MONTE_CARLO_SETTINGS) {
      const spec = section?.params.find((item) => item.name === name);
      const label = `${section?.label ?? "Monte Carlo"} · ${spec?.label ?? humanize(name)}`;
      rows.push(row(`monte_carlo.${name}`, label, spec?.unit ?? "", runs.map((run) => run.monteCarlo?.[name])));
    }
  }

  const filterLabels = new Map(runs.flatMap((run) => run.filters.map((filter) => [filter.name, filter.label] as const)));
  rows.push(row("filters", "Filters", "", runs.map((run) => run.filters.map((filter) => filter.label).join(", ") || "none")));
  if (runs.some((run) => run.benchmark)) rows.push(row("benchmark", "Benchmark", "", runs.map((run) => run.benchmark ?? undefined)));
  rows.push(
    ...ownedRows(
      "filter",
      filterLabels.keys(),
      (name) => filterLabels.get(name) ?? name,
      (name) => rules.filter_rules.find((rule) => rule.name === name)?.params ?? [],
      (run, name) => run.filters.find((filter) => filter.name === name)?.params,
      runs,
    ),
  );

  const entryLabels = new Map(runs.map((run) => [run.entry.name, run.entry.label]));
  rows.push(row("entry", "Entry", "", runs.map((run) => run.entry.label)));
  rows.push(
    ...ownedRows(
      "entry",
      entryLabels.keys(),
      (name) => entryLabels.get(name) ?? name,
      (name) => rules.entry_rules.find((rule) => rule.name === name)?.params ?? [],
      (run, name) => (run.entry.name === name ? run.entry.params : undefined),
      runs,
    ),
  );
  const exitLabels = new Map(runs.flatMap((run) => run.exits.map((exit) => [exit.name, exit.label] as const)));
  rows.push(row("exits", "Exits", "", runs.map((run) => run.exits.map((exit) => exit.label).join(", ") || "stop only")));
  rows.push(
    ...ownedRows(
      "exit",
      exitLabels.keys(),
      (name) => exitLabels.get(name) ?? name,
      (name) => rules.exit_rules.find((rule) => rule.name === name)?.params ?? [],
      (run, name) => run.exits.find((exit) => exit.name === name)?.params,
      runs,
    ),
  );
  rows.push(...priorityRows(runs, portfolios, rules));
  rows.push(...scanRows(runs, portfolios, sections, signals));

  rows.push(
    ...ownedRows(
      "params",
      new Set(runs.map((run) => run.signal)),
      (signal) => signal,
      (signal) => signals.find((item) => item.name === signal)?.params ?? [],
      (run, signal) => (run.signal === signal ? run.params : undefined),
      runs,
    ),
  );
  return rows;
}

/** A metric as a number for ranking; an infinite profit factor ranks above every finite one. */
export function metricValue(metrics: MetricsOut, key: MetricKey): number | null {
  if (key === "profit_factor" && metrics.profit_factor_infinite) return Infinity;
  const value = metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Positions holding the highest value; empty unless at least two values exist and they differ. */
export function bestIndexes(values: (number | null)[]): Set<number> {
  const present = values.filter((value): value is number => value !== null);
  if (present.length < 2) return new Set();
  const best = Math.max(...present);
  if (present.every((value) => value === best)) return new Set();
  return new Set(values.flatMap((value, index) => (value === best ? [index] : [])));
}

/** Equity as % return since the first point, so runs with different capital share one scale. */
export function returnCurve(points: Point[]): Point[] {
  const first = points[0]?.value;
  if (!first) return [];
  return points.map((point) => ({ time: point.time, value: (point.value / first - 1) * 100 }));
}
