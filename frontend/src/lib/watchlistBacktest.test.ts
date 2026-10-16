import { describe, expect, it } from "vitest";

import { config, watchlistResult } from "../test/fixtures";
import {
  backtestLink,
  formatMetric,
  readWatchlistForm,
  rowsToCsv,
  rowValue,
  spreadOf,
  spreadValue,
  watchlistBody,
  writeWatchlistForm,
} from "./watchlistBacktest";

describe("watchlist backtest form", () => {
  it("round-trips the universe and the setup without a ticker", () => {
    const url = "w=us_large&signal=connors_rsi2_long&filter=market&b=qqq&set.risk.atr_mult=2.5&exit=target&ex.target.target_r=3";
    const form = readWatchlistForm(new URLSearchParams(url), config);
    expect(form).toMatchObject({ universe: { watchlist: "us_large", tickers: "" }, signal: "connors_rsi2_long", benchmark: "QQQ" });
    expect("ticker" in form).toBe(false);
    expect(watchlistBody(form)).toEqual({
      watchlist: "us_large",
      signal: "connors_rsi2_long",
      period: null,
      params: {},
      settings: { risk: { atr_mult: 2.5 } },
      entry: { name: "next_open", params: {} },
      exits: [{ name: "target", params: { target_r: 3 } }],
      filters: [{ name: "market", params: {} }],
      benchmark: "QQQ",
    });
    expect(writeWatchlistForm(form, config).toString()).toBe(
      "w=us_large&signal=connors_rsi2_long&exit=target&filter=market&b=QQQ&set.risk.atr_mult=2.5&ex.target.target_r=3",
    );
  });

  it("takes ad-hoc tickers and needs a universe and a signal", () => {
    const form = readWatchlistForm(new URLSearchParams("t=aapl,msft&signal=golden_cross&ticker=SPY"), config);
    expect(watchlistBody(form)).toMatchObject({ tickers: ["AAPL", "MSFT"], signal: "golden_cross" });
    expect(watchlistBody(form)).not.toHaveProperty("ticker");
    expect(watchlistBody({ ...form, universe: { watchlist: "", tickers: " " } })).toBeNull();
    expect(watchlistBody({ ...form, signal: "" })).toBeNull();
  });
});

describe("watchlist backtest results", () => {
  const [aapl, msft] = watchlistResult.rows;

  it("links a ticker to its backtest with the benchmark the run compared", () => {
    const form = readWatchlistForm(new URLSearchParams("w=us_large&signal=connors_rsi2_long&filter=market"), config);
    expect(backtestLink(form, "AAPL", watchlistResult, config)).toBe(
      "/backtest?ticker=AAPL&signal=connors_rsi2_long&eng=vectorized&filter=market&b=SPY",
    );
  });

  it("reads values per period, with infinite profit factors and missing periods", () => {
    expect(rowValue(aapl!, "out_of_sample", "expectancy_r")).toBe(-0.1);
    expect(rowValue(msft!, "out_of_sample", "expectancy_r")).toBeNull();
    expect(rowValue(msft!, "full", "profit_factor")).toBe(Infinity);
    const profitFactor = spreadOf(watchlistResult, "full", "profit_factor");
    expect([spreadValue(profitFactor, "minimum"), spreadValue(profitFactor, "maximum")]).toEqual([1.6, Infinity]);
    expect(spreadValue(spreadOf(watchlistResult, "full", "sharpe"), "median")).toBeNull();
  });

  it("formats each metric in its own unit", () => {
    expect(formatMetric("expectancy_r", 0.25)).toBe("+0.25 R");
    expect(formatMetric("total_return_pct", 12.34)).toBe("+12.3%");
    expect(formatMetric("max_drawdown_pct", -9.31)).toBe("-9.3%");
    expect(formatMetric("trades", 12)).toBe("12");
    expect(formatMetric("profit_factor", Infinity)).toBe("∞");
    expect(formatMetric("sharpe", null)).toBe("–");
  });

  it("exports every metric of every period", () => {
    const [first, second] = rowsToCsv(watchlistResult);
    expect(first).toMatchObject({ ticker: "AAPL", oos_start: "2023-07-03", full_expectancy_r: 0.3, is_trades: 28, oos_expectancy_r: -0.1 });
    expect(second).toMatchObject({ ticker: "MSFT", oos_start: "", is_trades: null, oos_sharpe: null });
  });
});
