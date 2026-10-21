/**
 * Comparison of pinned runs: which parameters differ and which run is best on each metric.
 * Labels and units come from the API's parameter specs, so parameters added later appear without frontend changes.
 */
import type {
  AppliedRuleOut,
  ConfigOut,
  MetricsOut,
  ParamSpecOut,
  Point,
  SettingsSectionOut,
  SignalOut,
} from "../api/client";
import { MONTE_CARLO_SECTION, PORTFOLIO_SECTION, ROTATION_SECTION } from "./choices";
import { DASH } from "./format";
import { MONTE_CARLO_SETTINGS } from "./monteCarlo";
import type { RuleSpecs } from "./rules";
import {
  asBacktest,
  asPortfolio,
  asRotation,
  asSetup,
  type PinnedPortfolioRun,
  type PinnedRotationRun,
  type PinnedRun,
  type RunKind,
} from "./runs";

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
  if (typeof value === "object")
    return (
      Object.entries(value)
        .map(([key, item]) => `${key} ${display(item)}`)
        .join(", ") || "none"
    );
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
      rows.push(
        row(
          `${prefix}.${owner}.${name}`,
          `${labelOf(owner)} · ${spec?.label ?? humanize(name)}`,
          spec?.unit ?? "",
          params.map((item) => item?.[name]),
        ),
      );
    }
  }
  return rows;
}

/**
 * The rules' specs, with the priority rules when portfolio runs and the ranking and weighting rules when rotation runs
 * are compared.
 */
export type CompareSpecs = RuleSpecs & Partial<Pick<ConfigOut, "priority_rules" | "ranking_rules" | "weight_rules">>;

const KIND_LABELS: Record<RunKind, string> = { backtest: "Backtest", portfolio: "Portfolio", rotation: "Rotation" };

/** Each run as `as` gives it, undefined for the others; empty when `as` gives no run, so that kind's rows do not appear. */
function runsAs<R>(runs: PinnedRun[], as: (run: PinnedRun) => R | undefined): (R | undefined)[] {
  const found = runs.map(as);
  return found.some((run) => run !== undefined) ? found : [];
}

/** What a portfolio or a rotation run tested: its kind, universe and number of tickers. */
function universeRows(runs: PinnedRun[]): ParamRow[] {
  const universes = runsAs(runs, (run) => asPortfolio(run) ?? asRotation(run));
  if (!universes.length) return [];
  return [
    row(
      "kind",
      "Run",
      "",
      runs.map((run) => KIND_LABELS[run.kind]),
    ),
    row(
      "universe",
      "Universe",
      "",
      universes.map((run) => run?.universe),
    ),
    row(
      "tickers",
      "Tickers",
      "",
      universes.map((run) => run?.tickers.length),
    ),
  ];
}

/**
 * The rule a kind of run applies, by its label, and its parameters, keyed by rule so two rules' "lookback" never
 * share a row; `ruleOf` is undefined for runs without the rule.
 */
function appliedRuleRows(
  key: string,
  label: string,
  ruleOf: (run: PinnedRun) => AppliedRuleOut | undefined,
  specs: { name: string; params: ParamSpecOut[] }[] | undefined,
  runs: PinnedRun[],
): ParamRow[] {
  const applied = runs.map(ruleOf);
  const labels = new Map(applied.flatMap((rule) => (rule ? [[rule.name, rule.label] as const] : [])));
  return [
    row(
      key,
      label,
      "",
      applied.map((rule) => rule?.label),
    ),
    ...ownedRows(
      key,
      labels.keys(),
      (name) => labels.get(name) ?? name,
      (name) => specs?.find((rule) => rule.name === name)?.params ?? [],
      (run, name) => {
        const rule = ruleOf(run);
        return rule?.name === name ? rule.params : undefined;
      },
      runs,
    ),
  ];
}

/** The max positions and the max exposure of portfolio runs, labelled like the Portfolio page's fields. */
function portfolioSettingRows(
  portfolios: (PinnedPortfolioRun | undefined)[],
  sections: SettingsSectionOut[],
): ParamRow[] {
  const section = sections.find((item) => item.name === PORTFOLIO_SECTION);
  const settings = portfolios.map((run) => run?.portfolio as Record<string, number> | undefined);
  return keysOf(settings.filter((item) => item !== undefined)).map((name) => {
    const spec = section?.params.find((item) => item.name === name);
    return row(
      `portfolio.${name}`,
      `${section?.label ?? "Portfolio"} · ${spec?.label ?? humanize(name)}`,
      spec?.unit ?? "",
      settings.map((item) => item?.[name]),
    );
  });
}

/** The rule that ranked a portfolio's signals, with its parameters. */
function priorityRows(
  runs: PinnedRun[],
  portfolios: (PinnedPortfolioRun | undefined)[],
  rules: CompareSpecs,
): ParamRow[] {
  if (!portfolios.length) return [];
  return appliedRuleRows("priority", "Priority", (run) => asPortfolio(run)?.priority, rules.priority_rules, runs);
}

/**
 * What a rotation held: its holdings and absolute momentum lookback, labelled like the Rotation page's fields, its
 * rebalance and safe asset, the rules that ranked the tickers and weighted the picks with their parameters, and the
 * benchmark of its buy & hold.
 */
function rotationRows(
  runs: PinnedRun[],
  rotations: (PinnedRotationRun | undefined)[],
  sections: SettingsSectionOut[],
  rules: CompareSpecs,
): ParamRow[] {
  if (!rotations.length) return [];
  const section = sections.find((item) => item.name === ROTATION_SECTION);
  const settings: (Record<string, Raw> | undefined)[] = rotations.map(
    (run) => run && { ...run.rotation, safe_asset: run.rotation.safe_asset ?? "cash" },
  );
  return [
    ...keysOf(settings.filter((item) => item !== undefined)).map((name) => {
      const spec = section?.params.find((item) => item.name === name);
      return row(
        `rotation.${name}`,
        spec ? `${section?.label ?? "Rotation"} · ${spec.label}` : humanize(name),
        spec?.unit ?? "",
        settings.map((item) => item?.[name]),
      );
    }),
    ...appliedRuleRows("ranking", "Ranking", (run) => asRotation(run)?.ranking, rules.ranking_rules, runs),
    ...appliedRuleRows("weighting", "Weights", (run) => asRotation(run)?.weighting, rules.weight_rules, runs),
    row(
      "buy_hold_benchmark",
      "Buy & hold benchmark",
      "",
      rotations.map((run) => run?.buyHoldBenchmark),
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
      rows.push(
        row(
          `scan.${name}.${param}`,
          label,
          spec?.unit ?? "",
          settings.map((item) => item?.[param]),
        ),
      );
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

/** The Monte Carlo settings of the runs that have one. */
function monteCarloRows(runs: PinnedRun[], sections: SettingsSectionOut[]): ParamRow[] {
  const monteCarlos = runs.map((run) => asSetup(run)?.monteCarlo ?? undefined);
  if (!monteCarlos.some(Boolean)) return [];
  const section = sections.find((item) => item.name === MONTE_CARLO_SECTION);
  return MONTE_CARLO_SETTINGS.map((name) => {
    const spec = section?.params.find((item) => item.name === name);
    return row(
      `monte_carlo.${name}`,
      `${section?.label ?? "Monte Carlo"} · ${spec?.label ?? humanize(name)}`,
      spec?.unit ?? "",
      monteCarlos.map((monteCarlo) => monteCarlo?.[name]),
    );
  });
}

/** The entry filters (and the benchmark they compared) and the entry and exit rules, with their parameters. */
function tradeRuleRows(runs: PinnedRun[], rules: CompareSpecs): ParamRow[] {
  const setups = runs.map(asSetup);
  const present = setups.filter((run) => run !== undefined);
  const rows: ParamRow[] = [];
  const filterLabels = new Map(
    present.flatMap((run) => run.filters.map((filter) => [filter.name, filter.label] as const)),
  );
  rows.push(
    row(
      "filters",
      "Filters",
      "",
      setups.map((run) => run && (run.filters.map((filter) => filter.label).join(", ") || "none")),
    ),
  );
  if (present.some((run) => run.benchmark))
    rows.push(
      row(
        "benchmark",
        "Benchmark",
        "",
        setups.map((run) => run?.benchmark ?? undefined),
      ),
    );
  rows.push(
    ...ownedRows(
      "filter",
      filterLabels.keys(),
      (name) => filterLabels.get(name) ?? name,
      (name) => rules.filter_rules.find((rule) => rule.name === name)?.params ?? [],
      (run, name) => asSetup(run)?.filters.find((filter) => filter.name === name)?.params,
      runs,
    ),
  );
  rows.push(...appliedRuleRows("entry", "Entry", (run) => asSetup(run)?.entry, rules.entry_rules, runs));
  const exitLabels = new Map(present.flatMap((run) => run.exits.map((exit) => [exit.name, exit.label] as const)));
  rows.push(
    row(
      "exits",
      "Exits",
      "",
      setups.map((run) => run && (run.exits.map((exit) => exit.label).join(", ") || "stop only")),
    ),
  );
  rows.push(
    ...ownedRows(
      "exit",
      exitLabels.keys(),
      (name) => exitLabels.get(name) ?? name,
      (name) => rules.exit_rules.find((rule) => rule.name === name)?.params ?? [],
      (run, name) => asSetup(run)?.exits.find((exit) => exit.name === name)?.params,
      runs,
    ),
  );
  return rows;
}

/**
 * Every input of the runs as rows: what was tested (a ticker, or a portfolio's or a rotation's universe), the data
 * range, the stop, costs and account, a portfolio's max positions and max exposure, a rotation's holdings, absolute
 * momentum, rebalance, safe asset, ranking and weighting rules and buy & hold benchmark, the Monte Carlo settings, the
 * entry filters (and the benchmark they compared), the entry and exit rules with their parameters, a portfolio's
 * priority rule with its parameters and what it read of the scanner, and the signal parameters. Rows of a signal's
 * setup appear only when a backtest or a portfolio run is compared.
 */
export function parameterRows(
  runs: PinnedRun[],
  sections: SettingsSectionOut[] = [],
  signals: SignalOut[] = [],
  rules: CompareSpecs = { entry_rules: [], exit_rules: [], filter_rules: [] },
): ParamRow[] {
  const settingSpecs = sections.flatMap((section) => section.params);
  const setups = runsAs(runs, asSetup);
  const portfolios = runsAs(runs, asPortfolio);
  const rows: ParamRow[] = [...universeRows(runs)];
  if (setups.length)
    rows.push(
      row(
        "ticker",
        "Ticker",
        "",
        runs.map((run) => asBacktest(run)?.ticker),
      ),
      row(
        "signal",
        "Signal",
        "",
        setups.map((run) => run?.signal),
      ),
    );
  rows.push(
    row(
      "engine",
      "Engine",
      "",
      runs.map((run) => run.engine),
    ),
    row(
      "data",
      "Data",
      "",
      runs.map((run) => `${run.start} → ${run.end}`),
    ),
  );
  for (const name of keysOf(runs.map((run) => run.config))) {
    const spec = settingSpecs.find((item) => item.name === name);
    const values = runs.map((run) => (run.config as unknown as Record<string, number | undefined>)[name]);
    rows.push(row(`config.${name}`, spec?.label ?? humanize(name), spec?.unit ?? "", values));
  }
  rows.push(...portfolioSettingRows(portfolios, sections));
  rows.push(...rotationRows(runs, runsAs(runs, asRotation), sections, rules));
  if (!setups.length) return rows;

  rows.push(...monteCarloRows(runs, sections));
  rows.push(...tradeRuleRows(runs, rules));
  rows.push(...priorityRows(runs, portfolios, rules));
  rows.push(...scanRows(runs, portfolios, sections, signals));
  rows.push(
    ...ownedRows(
      "params",
      new Set(setups.flatMap((run) => (run ? [run.signal] : []))),
      (signal) => signal,
      (signal) => signals.find((item) => item.name === signal)?.params ?? [],
      (run, signal) => {
        const setup = asSetup(run);
        return setup?.signal === signal ? setup.params : undefined;
      },
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
