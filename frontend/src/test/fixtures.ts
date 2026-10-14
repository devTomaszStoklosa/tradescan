import type { AppliedRuleOut, BacktestOut, ConfigOut, HitOut, MetricsOut, ParamSpecOut, RuleOut, ScanOut, SignalOut, WatchlistOut } from "../api/client";
import { formatTemplate } from "../lib/overrides";
import type { BacktestForm } from "../lib/params";
import { toPinnedRun, type PinnedRun, type RunSnapshot } from "../lib/runs";

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
      ],
    },
  ],
  families: ["trend", "momentum", "breakout", "mean_reversion", "volume", "pattern"],
  engines: ["vectorized", "cerebro"],
  entry_rules: entryRules,
  exit_rules: exitRules,
  default_entry: "next_open",
  default_exits: ["target", "time"],
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
  },
  entry: appliedRule(entryRules[0]!),
  exits: exitRules.map((rule) => appliedRule(rule)),
  buy_hold: [
    { time: "2016-01-04", value: 100000 },
    { time: "2026-10-13", value: 130200 },
  ],
  runs: [
    {
      engine: "vectorized",
      metrics: makeMetrics(),
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
};

/** A pinned run of `backtestResult`, changed by `overrides`, with a fixed slot. */
export function makeRun(slot: number, overrides: Partial<RunSnapshot> = {}, extra: Partial<PinnedRun> = {}): PinnedRun {
  const snapshot: RunSnapshot = {
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
    metrics: makeMetrics(),
    equity: backtestResult.runs[0]!.equity,
    form: backtestForm,
    ...overrides,
  };
  return { ...toPinnedRun(snapshot, new Date("2026-10-14T09:00:00Z")), id: `run-${slot}`, slot, ...extra };
}
