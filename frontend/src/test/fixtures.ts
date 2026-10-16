import type {
  AppliedRuleOut,
  BacktestOut,
  ConfigOut,
  FilterRuleOut,
  HitOut,
  MetricsOut,
  MetricSpreadOut,
  MonteCarloOut,
  ParamSpecOut,
  PortfolioOut,
  PortfolioRunOut,
  PortfolioStatsOut,
  RuleOut,
  ScanOut,
  SignalOut,
  SweepOut,
  WatchlistBacktestOut,
  WatchlistOut,
} from "../api/client";
import { formatTemplate } from "../lib/overrides";
import type { BacktestForm } from "../lib/params";
import type { PortfolioForm } from "../lib/portfolio";
import {
  snapshotPortfolioRun,
  toPinnedRun,
  type BacktestSnapshot,
  type PinnedBacktestRun,
  type PinnedPortfolioRun,
  type PinnedRun,
  type PortfolioSnapshot,
} from "../lib/runs";

export function spec(
  name: string,
  label: string,
  value: ParamSpecOut["default"],
  [minimum, maximum, step]: [number, number, number],
  kind: ParamSpecOut["kind"] = "float",
  extra: Partial<ParamSpecOut> = {},
): ParamSpecOut {
  return { name, kind, label, unit: "", help: "", default: value, minimum, maximum, step, keys: null, ...extra };
}

const FAMILY_WEIGHTS = { trend: 1, momentum: 1, breakout: 1.5, mean_reversion: 1, volume: 1, pattern: 0.5 };

const VALID_BARS = spec("valid_bars", "Active for", 1, [1, 20, 1], "int", { unit: "bars" });

/** What /api/config lists as entry rules. */
export const entryRules: RuleOut[] = [
  {
    name: "next_open",
    label: "Next open",
    description: "Market order at the next open; stop and target are measured from the signal bar's close",
    template: "Market order at the next open; stop and target are measured from the signal bar's close",
    params: [],
  },
  {
    name: "stop",
    label: "Stop order",
    description: "Buy-stop 0 ATR above the signal bar's high (sell-stop below its low for shorts), active for 1 bar(s)",
    template: "Buy-stop {offset_atr:g} ATR above the signal bar's high (sell-stop below its low for shorts), active for {valid_bars} bar(s)",
    params: [spec("offset_atr", "Offset", 0, [0, 5, 0.05], "float", { unit: "ATR" }), VALID_BARS],
  },
  {
    name: "limit",
    label: "Limit order",
    description: "Buy-limit 0.5 ATR below the signal bar's close (sell-limit above it for shorts), active for 1 bar(s)",
    template: "Buy-limit {offset_atr:g} ATR below the signal bar's close (sell-limit above it for shorts), active for {valid_bars} bar(s)",
    params: [spec("offset_atr", "Offset", 0.5, [0, 5, 0.05], "float", { unit: "ATR" }), VALID_BARS],
  },
];

/** What /api/config lists as exit rules. */
export const exitRules: RuleOut[] = [
  {
    name: "target",
    label: "Profit target",
    description: "Limit order 2R from the entry reference",
    template: "Limit order {target_r:g}R from the entry reference",
    params: [spec("target_r", "Distance", 2, [0.25, 50, 0.25], "float", { unit: "R" })],
  },
  {
    name: "time",
    label: "Time exit",
    description: "Exit at the open 20 bars after the entry bar",
    template: "Exit at the open {max_hold_bars} bars after the entry bar",
    params: [spec("max_hold_bars", "Hold for", 20, [1, 1000, 1], "int", { unit: "bars" })],
  },
];

/** What /api/config lists as entry filters. */
export const filterRules: FilterRuleOut[] = [
  {
    name: "trend",
    label: "Trend filter",
    description: "Close above SMA(200) for longs, below it for shorts",
    template: "Close above SMA({period}) for longs, below it for shorts",
    params: [spec("period", "SMA length", 200, [2, 400, 1], "int", { unit: "bars" })],
    needs_benchmark: false,
  },
  {
    name: "market",
    label: "Market filter",
    description: "Benchmark close above its SMA(200) for longs, below it for shorts",
    template: "Benchmark close above its SMA({period}) for longs, below it for shorts",
    params: [spec("period", "Benchmark SMA", 200, [2, 400, 1], "int", { unit: "bars" })],
    needs_benchmark: true,
  },
];

/** What /api/config lists as priority rules of a portfolio backtest. */
export const priorityRules: RuleOut[] = [
  {
    name: "relative_strength",
    label: "Relative strength",
    description: "Weighted returns over several lookbacks (IBD style by default: the latest quarter counts double)",
    template: "Weighted returns over several lookbacks (IBD style by default: the latest quarter counts double)",
    params: [
      spec("periods", "Lookbacks", [63, 126, 189, 252], [1, 1000, 1], "int_list", { unit: "bars" }),
      spec("weights", "Weights", [0.4, 0.2, 0.2, 0.2], [0, 10, 0.05], "float_list"),
    ],
  },
  {
    name: "momentum",
    label: "Momentum",
    description: "Return from 252 bars ago to 21 bars ago",
    template: "Return from {lookback} bars ago to {skip} bars ago",
    params: [spec("lookback", "Lookback", 252, [2, 1000, 1], "int", { unit: "bars" }), spec("skip", "Skip", 21, [0, 250, 1], "int", { unit: "bars" })],
  },
];

/** A rule as a backtest result reports it. */
export function appliedRule(rule: RuleOut, params: Record<string, number> = {}): AppliedRuleOut {
  const values = { ...Object.fromEntries(rule.params.map((item) => [item.name, item.default as number])), ...params };
  return { name: rule.name, label: rule.label, description: formatTemplate(rule.template, values), params: values };
}

/** A trimmed copy of what /api/config returns. */
export const config: ConfigOut = {
  version: "0.1.0",
  scan_period: "5y",
  backtest_period: "10y",
  benchmark: "SPY",
  sections: [
    {
      name: "account",
      label: "Account",
      params: [
        spec("equity", "Account equity", 100000, [1, 1e12, 1000]),
        spec("risk_pct", "Risk per trade", 1, [0.01, 100, 0.1], "float", { unit: "%" }),
        spec("max_position_pct", "Max position", 25, [0.1, 100, 1], "float", { unit: "% of equity" }),
        spec("lot_size", "Lot size", 1, [1e-8, 1e6, 0.0001]),
      ],
    },
    {
      name: "risk",
      label: "Risk plan",
      params: [
        spec("atr_period", "ATR period", 14, [2, 100, 1], "int", { unit: "bars" }),
        spec("atr_mult", "Stop distance", 2, [0.25, 20, 0.25], "float", { unit: "ATR" }),
        spec("targets_r", "Scan targets", [2, 3], [0.25, 50, 0.25], "float_list", { unit: "R" }),
      ],
    },
    {
      name: "scan",
      label: "Scan",
      params: [
        spec("fresh_bars", "Fresh within", 3, [1, 60, 1], "int", { unit: "bars" }),
        spec("min_score", "Minimum score", 1, [-50, 100, 0.5]),
        spec("edge_horizon", "Edge horizon", 10, [1, 250, 1], "int", { unit: "bars" }),
      ],
    },
    {
      name: "scoring",
      label: "Scoring",
      params: [
        spec("trend_bonus", "Daily trend bonus", 1, [0, 10, 0.5]),
        spec("family_weights", "Family weights", FAMILY_WEIGHTS, [-10, 10, 0.5], "weights", { keys: Object.keys(FAMILY_WEIGHTS) }),
        spec("signal_weights", "Signal weights", {}, [-10, 10, 0.5], "weights"),
      ],
    },
    {
      name: "backtest",
      label: "Backtest",
      params: [
        spec("commission_pct", "Commission", 0.1, [0, 5, 0.01], "float", { unit: "%" }),
        spec("slippage_pct", "Slippage", 0.05, [0, 5, 0.01], "float", { unit: "%" }),
        spec("oos_pct", "Out-of-sample share", 30, [10, 50, 5], "float", { unit: "% of history" }),
      ],
    },
    {
      name: "monte_carlo",
      label: "Monte Carlo",
      params: [
        spec("simulations", "Simulations", 1000, [100, 10000, 100], "int"),
        spec("ruin_drawdown_pct", "Ruin level", 50, [1, 100, 5], "float", { unit: "% drawdown" }),
        spec("seed", "Random seed", 0, [0, 2147483647, 1], "int"),
      ],
    },
    {
      name: "portfolio",
      label: "Portfolio",
      params: [
        spec("max_positions", "Max positions", 10, [1, 100, 1], "int"),
        spec("max_exposure_pct", "Max exposure", 100, [1, 300, 5], "float", { unit: "% of equity" }),
      ],
    },
  ],
  families: ["trend", "momentum", "breakout", "mean_reversion", "volume", "pattern"],
  engines: ["vectorized", "cerebro"],
  entry_rules: entryRules,
  exit_rules: exitRules,
  filter_rules: filterRules,
  default_entry: "next_open",
  default_exits: ["target", "time"],
  priority_rules: priorityRules,
  default_priority: "relative_strength",
  sweep: {
    max_axes: 2,
    min_values: 2,
    max_values: 50,
    max_combinations: 200,
    sections: ["account", "risk", "backtest"],
    fixed: ["backtest.oos_pct"],
    min_period_bars: 60,
  },
};

/** A trimmed copy of what /api/signals returns. */
export const signals: SignalOut[] = [
  {
    name: "donchian_breakout",
    family: "breakout",
    direction: "long",
    weight: 1.5,
    description: "Close above the highest high of the previous 20 bars (Turtle entry)",
    template: "Close above the highest high of the previous {period} bars (Turtle entry)",
    params: [spec("period", "Channel length", 20, [2, 300, 1], "int", { unit: "bars" })],
  },
  {
    name: "connors_rsi2_long",
    family: "mean_reversion",
    direction: "long",
    weight: 1,
    description: "RSI(2) < 10 while price is above SMA(200): dip in an uptrend",
    template: "RSI({rsi_period}) < {oversold:g} while price is above SMA({trend_period}): dip in an uptrend",
    params: [
      spec("rsi_period", "RSI period", 2, [2, 30, 1], "int", { unit: "bars" }),
      spec("trend_period", "Trend SMA", 200, [10, 400, 1], "int", { unit: "bars" }),
      spec("oversold", "Oversold level", 10, [1, 50, 1]),
    ],
  },
];

export const watchlists: WatchlistOut[] = [
  { name: "us_large", tickers: ["AAPL", "MSFT"], benchmark: "SPY" },
  { name: "wig20", tickers: ["PKO.WA"], benchmark: "ETFBW20TR.WA" },
];

export function makeHit(overrides: Partial<HitOut> = {}): HitOut {
  return {
    ticker: "AAPL",
    direction: "long",
    date: "2026-10-12",
    close: 200,
    change_pct: 1.5,
    atr: 4,
    atr_pct: 2,
    adx: 25,
    daily_trend: "up",
    weekly_trend: "up",
    rs_percentile: 90,
    fired: [{ name: "donchian_breakout", family: "breakout", bars_ago: 0, weight: 1.5 }],
    score: { total: 4.5, signals: 1.5, trend: 1, weekly: 1, relative_strength: 1 },
    risk: { entry: 200, stop: 192, targets: [216, 224], risk_per_share: 8, size: 125, position_value: 25000, risk_amount: 1000 },
    edge: {
      signal: "donchian_breakout",
      horizon: 10,
      events: 42,
      win_rate: 57,
      mean_return: 1.2,
      median_return: 0.9,
      baseline_return: 0.5,
      edge: 0.7,
    },
    ...overrides,
  };
}

export const scanResult: ScanOut = {
  universe: "us_large",
  regime: {
    benchmark: "SPY",
    benchmark_close: 500,
    benchmark_above_slow: true,
    benchmark_fast_above_slow: true,
    pct_above_fast: 70,
    pct_above_slow: 80,
    new_highs: 2,
    new_lows: 0,
    universe_size: 2,
    regime: "risk-on",
  },
  hits: [makeHit(), makeHit({ ticker: "MSFT", direction: "short", score: { total: 2, signals: 1, trend: 0, weekly: 0, relative_strength: 1 }, edge: null })],
  missing: [],
  skipped: [],
  min_score: 1,
  fresh_bars: 3,
  edge_horizon: 10,
};

export function makeMetrics(overrides: Partial<MetricsOut> = {}): MetricsOut {
  return {
    total_return_pct: 12.5,
    cagr_pct: 4.1,
    sharpe: 0.8,
    sortino: 1.1,
    max_drawdown_pct: -9.3,
    trades: 42,
    win_rate_pct: 61.9,
    profit_factor: 1.6,
    profit_factor_infinite: false,
    expectancy_r: 0.21,
    sqn: 1.9,
    exposure_pct: 18,
    buy_hold_pct: 30.2,
    ...overrides,
  };
}

/** The Monte Carlo of 42 trades: shuffling keeps the final return, bootstrapping spreads it. */
export function makeMonteCarlo(overrides: Partial<MonteCarloOut> = {}): MonteCarloOut {
  return {
    simulations: 1000,
    ruin_drawdown_pct: 50,
    seed: 0,
    risk_pct: 1,
    trades: 42,
    actual: { final_return_pct: 9.1, max_drawdown_pct: -6.2, longest_losing_streak: 5 },
    methods: [
      {
        name: "shuffled",
        label: "Shuffled",
        description: "The same trades in a random order; the final return stays the same",
        final_return_pct: { p5: 9.1, p25: 9.1, p50: 9.1, p75: 9.1, p95: 9.1 },
        max_drawdown_pct: { p5: -14.8, p25: -10.2, p50: -8.4, p75: -6.9, p95: -5.1 },
        longest_losing_streak: { p5: 4, p25: 5, p50: 6, p75: 7, p95: 9 },
        ruin_pct: 0,
      },
      {
        name: "bootstrapped",
        label: "Bootstrapped",
        description: "As many trades drawn at random with replacement",
        final_return_pct: { p5: -7.3, p25: 2.4, p50: 8.8, p75: 15.6, p95: 26.4 },
        max_drawdown_pct: { p5: -21.5, p25: -13.1, p50: -9.7, p75: -7.2, p95: -4.8 },
        longest_losing_streak: { p5: 4, p25: 5, p50: 6.5, p75: 8, p95: 10 },
        ruin_pct: 0.4,
      },
    ],
    ...overrides,
  };
}

export const backtestResult: BacktestOut = {
  ticker: "SPY",
  signal: "connors_rsi2_long",
  direction: "long",
  description: "RSI(2) < 10 while price is above SMA(200): dip in an uptrend",
  params: { rsi_period: 2, trend_period: 200, oversold: 10 },
  start: "2016-01-04",
  end: "2026-10-13",
  config: {
    initial_equity: 100000,
    risk_pct: 1,
    max_position_pct: 25,
    lot_size: 1,
    atr_period: 14,
    atr_mult: 2,
    commission_pct: 0.1,
    slippage_pct: 0.05,
    bars_per_year: 252,
    oos_pct: 30,
  },
  entry: appliedRule(entryRules[0]!),
  exits: exitRules.map((rule) => appliedRule(rule)),
  filters: [],
  benchmark: null,
  split: {
    oos_pct: 30,
    in_sample_start: "2016-01-04",
    in_sample_end: "2023-06-30",
    out_of_sample_start: "2023-07-03",
    out_of_sample_end: "2026-10-13",
  },
  buy_hold: [
    { time: "2016-01-04", value: 100000 },
    { time: "2026-10-13", value: 130200 },
  ],
  runs: [
    {
      engine: "vectorized",
      metrics: makeMetrics(),
      in_sample: makeMetrics({ sharpe: 1.1, trades: 30 }),
      out_of_sample: makeMetrics({ sharpe: 0.2, trades: 12 }),
      monte_carlo: makeMonteCarlo(),
      equity: [
        { time: "2016-01-04", value: 100000 },
        { time: "2021-06-01", value: 105000.123 },
        { time: "2026-10-13", value: 112500 },
      ],
      trades: [],
    },
  ],
};

export const backtestForm: BacktestForm = {
  ticker: "SPY",
  signal: "connors_rsi2_long",
  engines: ["vectorized"],
  period: "",
  settings: {},
  signalParams: {},
  entry: "next_open",
  entryParams: {},
  exits: ["target", "time"],
  exitParams: {},
  filters: [],
  filterParams: {},
  benchmark: "",
};

type PinFields = Pick<PinnedRun, "id" | "slot" | "name" | "pinnedAt" | "hidden">;

/** A pinned run of `backtestResult`, changed by `overrides`, with a fixed slot. */
export function makeRun(slot: number, overrides: Partial<BacktestSnapshot> = {}, extra: Partial<PinFields> = {}): PinnedBacktestRun {
  const snapshot: BacktestSnapshot = {
    kind: "backtest",
    ticker: backtestResult.ticker,
    signal: backtestResult.signal,
    direction: backtestResult.direction,
    description: backtestResult.description,
    engine: "vectorized",
    start: backtestResult.start,
    end: backtestResult.end,
    params: backtestResult.params,
    config: backtestResult.config,
    entry: backtestResult.entry,
    exits: backtestResult.exits,
    filters: backtestResult.filters,
    benchmark: backtestResult.benchmark,
    metrics: makeMetrics(),
    split: { ...backtestResult.split!, in_sample: makeMetrics({ sharpe: 1.1, trades: 30 }), out_of_sample: makeMetrics({ sharpe: 0.2, trades: 12 }) },
    monteCarlo: makeMonteCarlo(),
    equity: backtestResult.runs[0]!.equity,
    form: backtestForm,
    ...overrides,
  };
  return { ...toPinnedRun(snapshot, new Date("2026-10-14T09:00:00Z")), id: `run-${slot}`, slot, ...extra };
}

const sweepCell = (values: number[], sharpe: [number, number], trades: [number, number] = [30, 25]) => ({
  values,
  in_sample: makeMetrics({ sharpe: sharpe[0], trades: trades[0] }),
  out_of_sample: makeMetrics({ sharpe: sharpe[1], trades: trades[1] }),
  error: null,
});

/** A 3 × 2 sweep of the RSI2 setup: oversold 5/10/15 by target 2R/3R, one combination failed. */
export const sweepResult: SweepOut = {
  ticker: "SPY",
  signal: "connors_rsi2_long",
  direction: "long",
  description: backtestResult.description,
  params: backtestResult.params,
  start: backtestResult.start,
  end: backtestResult.end,
  config: backtestResult.config,
  entry: backtestResult.entry,
  exits: backtestResult.exits,
  filters: backtestResult.filters,
  benchmark: backtestResult.benchmark,
  engine: "vectorized",
  split: backtestResult.split!,
  axes: [
    { target: "signal", owner: null, name: "oversold", key: "signal.oversold", label: "Oversold level", unit: "", kind: "float", current: 10, values: [5, 10, 15] },
    { target: "exit", owner: "target", name: "target_r", key: "exit.target.target_r", label: "Distance", unit: "R", kind: "float", current: 2, values: [2, 3] },
  ],
  cells: [
    sweepCell([5, 2], [0.4, 0.1]),
    sweepCell([5, 3], [0.6, -0.2]),
    sweepCell([10, 2], [0.9, 0.5]),
    sweepCell([10, 3], [1.4, 0.3], [30, 8]),
    sweepCell([15, 2], [0.7, 0.4]),
    { values: [15, 3], in_sample: null, out_of_sample: null, error: "connors_rsi2_long: test failure" },
  ],
};

const spread = (metric: string, values: Partial<MetricSpreadOut>): MetricSpreadOut => ({
  metric,
  tickers: 2,
  median: null,
  p25: null,
  p75: null,
  minimum: null,
  maximum: null,
  above_break_even_pct: null,
  ...values,
});

/** The RSI2 setup with the market filter on us_large: AAPL holds up, MSFT is too short to split, TSLA had no data. */
export const watchlistResult: WatchlistBacktestOut = {
  signal: "connors_rsi2_long",
  direction: "long",
  description: backtestResult.description,
  params: backtestResult.params,
  config: backtestResult.config,
  entry: backtestResult.entry,
  exits: backtestResult.exits,
  filters: [appliedRule(filterRules[1]!)],
  benchmark: "SPY",
  universe: "us_large",
  engine: "vectorized",
  rows: [
    {
      ticker: "AAPL",
      start: "2016-01-04",
      end: "2026-10-13",
      split: backtestResult.split,
      metrics: makeMetrics({ expectancy_r: 0.3, trades: 40 }),
      in_sample: makeMetrics({ expectancy_r: 0.4, trades: 28 }),
      out_of_sample: makeMetrics({ expectancy_r: -0.1, trades: 12 }),
    },
    {
      ticker: "MSFT",
      start: "2026-03-02",
      end: "2026-10-13",
      split: null,
      metrics: makeMetrics({ expectancy_r: 0.5, trades: 6, profit_factor: null, profit_factor_infinite: true }),
      in_sample: null,
      out_of_sample: null,
    },
  ],
  periods: [
    {
      period: "full",
      tickers: 2,
      pooled: { trades: 46, win_rate_pct: 58.7, expectancy_r: 0.33, profit_factor_r: 1.8, profit_factor_infinite: false, sqn: 2.1 },
      spread: [
        spread("expectancy_r", { median: 0.4, p25: 0.35, p75: 0.45, minimum: 0.3, maximum: 0.5, above_break_even_pct: 100 }),
        spread("profit_factor", { median: null, p25: 1.6, p75: null, minimum: 1.6, maximum: null, above_break_even_pct: 100 }),
      ],
    },
    {
      period: "in_sample",
      tickers: 1,
      pooled: { trades: 28, win_rate_pct: 60, expectancy_r: 0.4, profit_factor_r: 2, profit_factor_infinite: false, sqn: 2.3 },
      spread: [spread("expectancy_r", { tickers: 1, median: 0.4, p25: 0.4, p75: 0.4, minimum: 0.4, maximum: 0.4, above_break_even_pct: 100 })],
    },
    {
      period: "out_of_sample",
      tickers: 1,
      pooled: { trades: 12, win_rate_pct: 41.7, expectancy_r: -0.1, profit_factor_r: 0.8, profit_factor_infinite: false, sqn: -0.4 },
      spread: [spread("expectancy_r", { tickers: 1, median: -0.1, p25: -0.1, p75: -0.1, minimum: -0.1, maximum: -0.1, above_break_even_pct: 0 })],
    },
  ],
  missing: ["TSLA"],
};

const portfolioStats = (overrides: Partial<PortfolioStatsOut> = {}): PortfolioStatsOut => ({
  average_positions: 2.4,
  max_positions: 5,
  average_exposure_pct: 48.5,
  max_exposure_pct: 100.9,
  orders: 120,
  skipped_no_slot: 30,
  skipped_no_room: 4,
  ...overrides,
});

export function makePortfolioRun(engine: string, overrides: Partial<PortfolioRunOut> = {}): PortfolioRunOut {
  return {
    engine,
    full: { metrics: makeMetrics({ trades: 118, buy_hold_pct: 180.5 }), stats: portfolioStats() },
    in_sample: { metrics: makeMetrics({ sharpe: 1.1, trades: 80 }), stats: portfolioStats({ orders: 82 }) },
    out_of_sample: { metrics: makeMetrics({ sharpe: 0.3, trades: 38 }), stats: portfolioStats({ orders: 38, skipped_no_room: 0 }) },
    equity: [
      { time: "2016-01-04", value: 100000 },
      { time: "2026-10-13", value: 115000 },
    ],
    positions: [
      { time: "2016-01-04", value: 0 },
      { time: "2026-10-13", value: 3 },
    ],
    trades: [
      {
        ticker: "AAPL", direction: "long", signal_date: "2024-03-01", entry_date: "2024-03-04", exit_date: "2024-03-08",
        entry_price: 170, exit_price: 178, size: 100, pnl: 780, r_multiple: 1.6, exit_reason: "target",
      },
      {
        ticker: "MSFT", direction: "long", signal_date: "2024-03-01", entry_date: "2024-03-04", exit_date: "2024-03-06",
        entry_price: 400, exit_price: 390, size: 40, pnl: -430, r_multiple: -1.05, exit_reason: "stop",
      },
    ],
    tickers: [
      { ticker: "AAPL", trades: 70, pnl: 18000, contribution_pct: 18, win_rate_pct: 55, expectancy_r: 0.3 },
      { ticker: "MSFT", trades: 48, pnl: -3000, contribution_pct: -3, win_rate_pct: 40, expectancy_r: -0.1 },
    ],
    ...overrides,
  };
}

/** The RSI2 setup with the market filter on us_large as one portfolio, ranked by momentum; TSLA had no data. */
export const portfolioResult: PortfolioOut = {
  signal: "connors_rsi2_long",
  direction: "long",
  description: backtestResult.description,
  params: backtestResult.params,
  config: backtestResult.config,
  entry: backtestResult.entry,
  exits: backtestResult.exits,
  filters: [appliedRule(filterRules[1]!)],
  benchmark: "SPY",
  universe: "us_large",
  start: "2016-01-04",
  end: "2026-10-13",
  portfolio: { max_positions: 5, max_exposure_pct: 100 },
  priority: appliedRule(priorityRules[1]!),
  buy_hold_benchmark: "SPY",
  buy_hold: backtestResult.buy_hold,
  split: backtestResult.split,
  runs: [makePortfolioRun("vectorized")],
  missing: ["TSLA"],
};

const { ticker: _ticker, ...portfolioSetup } = backtestForm;

export const portfolioForm: PortfolioForm = {
  ...portfolioSetup,
  universe: { watchlist: "us_large", tickers: "" },
  filters: ["market"],
  priority: "momentum",
  priorityParams: {},
};

/** A pinned run of `portfolioResult`, changed by `overrides`, with a fixed slot. */
export function makePortfolioPin(slot: number, overrides: Partial<PortfolioSnapshot> = {}, extra: Partial<PinFields> = {}): PinnedPortfolioRun {
  const snapshot = snapshotPortfolioRun(portfolioResult, "vectorized", portfolioForm)!;
  return { ...toPinnedRun({ ...snapshot, ...overrides }, new Date("2026-10-14T09:00:00Z")), id: `portfolio-${slot}`, slot, ...extra };
}
