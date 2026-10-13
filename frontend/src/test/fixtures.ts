import type { ConfigOut, HitOut, ScanOut, WatchlistOut } from "../api/client";

export const config: ConfigOut = {
  version: "0.1.0",
  account: { equity: 100000, risk_pct: 1, max_position_pct: 25, lot_size: 1 },
  scan: { fresh_bars: 3, min_score: 1, edge_horizon: 10, benchmark: "SPY", period: "5y" },
  backtest: { period: "10y", atr_mult: 2, target_r: 2, max_hold_bars: 20, commission_pct: 0.1, slippage_pct: 0.05 },
  targets_r: [2, 3],
  families: ["trend", "momentum", "breakout", "mean_reversion", "volume", "pattern"],
  engines: ["vectorized", "cerebro"],
};

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
