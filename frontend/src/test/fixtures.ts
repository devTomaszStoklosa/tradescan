import type { ConfigOut, HitOut, ParamSpecOut, ScanOut, SignalOut, WatchlistOut } from "../api/client";

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
        spec("target_r", "Target", 2, [0.25, 50, 0.25], "float", { unit: "R" }),
        spec("max_hold_bars", "Time exit", 20, [1, 1000, 1], "int", { unit: "bars" }),
      ],
    },
  ],
  families: ["trend", "momentum", "breakout", "mean_reversion", "volume", "pattern"],
  engines: ["vectorized", "cerebro"],
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
