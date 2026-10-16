import { describe, expect, it } from "vitest";

import { config } from "../test/fixtures";
import {
  backtestLink,
  hasPriorityProblems,
  portfolioBody,
  priorityChanges,
  readPortfolioForm,
  resetPortfolio,
  watchlistLink,
  writePortfolioForm,
} from "./portfolio";

const URL = "w=us_large&signal=connors_rsi2_long&eng=vectorized,cerebro&filter=market&b=QQQ&set.portfolio.max_positions=5&set.risk.atr_mult=3&prio=momentum&pr.momentum.skip=0";

describe("portfolio form", () => {
  it("round-trips the universe, the setup, the engines and the priority through the URL", () => {
    const form = readPortfolioForm(new URLSearchParams(URL), config);
    expect(form).toMatchObject({
      universe: { watchlist: "us_large", tickers: "" },
      signal: "connors_rsi2_long",
      engines: ["vectorized", "cerebro"],
      filters: ["market"],
      benchmark: "QQQ",
      settings: { portfolio: { max_positions: 5 }, risk: { atr_mult: 3 } },
      priority: "momentum",
      priorityParams: { skip: 0 },
    });
    expect(writePortfolioForm(form, config).toString()).toBe(new URLSearchParams(URL).toString());
  });

  it("leaves the defaults out of the URL and reads them back", () => {
    const form = readPortfolioForm(new URLSearchParams("t=AAPL,MSFT&signal=connors_rsi2_long"), config);
    expect(form).toMatchObject({ engines: ["vectorized"], priority: "relative_strength", priorityParams: {} });
    expect(writePortfolioForm(form, config).toString()).toBe("t=AAPL%2CMSFT&signal=connors_rsi2_long&eng=vectorized");
  });

  it("builds the request with the priority rule and its parameters", () => {
    const form = readPortfolioForm(new URLSearchParams(URL), config);
    expect(portfolioBody(form)).toMatchObject({
      watchlist: "us_large",
      signal: "connors_rsi2_long",
      engines: ["vectorized", "cerebro"],
      priority: { name: "momentum", params: { skip: 0 } },
      settings: { portfolio: { max_positions: 5 } },
    });
    expect(portfolioBody({ ...form, engines: [] })).toBeNull();
    expect(portfolioBody({ ...form, universe: { watchlist: "", tickers: " " } })).toBeNull();
  });

  it("counts, checks and resets the priority rule", () => {
    const form = readPortfolioForm(new URLSearchParams(URL), config);
    expect(priorityChanges(form, config)).toBe(2);
    expect(hasPriorityProblems(form, config)).toBe(false);
    expect(hasPriorityProblems({ ...form, priorityParams: { skip: 300 } }, config)).toBe(true);
    expect(hasPriorityProblems({ ...form, priority: "nope" }, config)).toBe(true);
    const reset = resetPortfolio(form, config);
    expect(reset).toMatchObject({ priority: "relative_strength", priorityParams: {}, settings: {}, filters: [], engines: ["vectorized", "cerebro"] });
    expect(reset.universe).toEqual(form.universe);
  });

  it("links one ticker to the Backtest page and the setup to the Watchlist page without the portfolio's settings", () => {
    const form = readPortfolioForm(new URLSearchParams(URL), config);
    expect(backtestLink(form, "AAPL", "cerebro", "SPY", config)).toBe(
      "/backtest?ticker=AAPL&signal=connors_rsi2_long&eng=cerebro&filter=market&b=SPY&set.risk.atr_mult=3",
    );
    expect(backtestLink(form, "AAPL", "vectorized", null, config)).toContain("b=QQQ");
    expect(watchlistLink(form, config)).toBe("/watchlist?w=us_large&signal=connors_rsi2_long&filter=market&b=QQQ&set.risk.atr_mult=3");
  });
});
