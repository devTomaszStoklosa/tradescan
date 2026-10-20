import { describe, expect, it } from "vitest";

import { config, signals } from "../test/fixtures";
import { pickSections } from "./overrides";
import {
  backtestLink,
  choosePriority,
  hasPriorityProblems,
  hasScoreSignalProblems,
  portfolioBody,
  portfolioSections,
  priorityChanges,
  readPortfolioForm,
  resetPortfolio,
  scoreExclusions,
  scoreSignals,
  watchlistLink,
  withCountedScoreSignals,
  writePortfolioForm,
} from "./portfolio";

const URL =
  "w=us_large&signal=connors_rsi2_long&eng=vectorized,cerebro&filter=market&b=QQQ&set.portfolio.max_positions=5&set.risk.atr_mult=3&prio=momentum&pr.momentum.skip=0";

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
    expect(reset).toMatchObject({
      priority: "relative_strength",
      priorityParams: {},
      settings: {},
      filters: [],
      engines: ["vectorized", "cerebro"],
    });
    expect(reset.universe).toEqual(form.universe);
  });

  it("links one ticker to the Backtest page and the setup to the Watchlist page without the portfolio's settings", () => {
    const form = readPortfolioForm(new URLSearchParams(URL), config);
    expect(backtestLink(form, "AAPL", "cerebro", "SPY", config)).toBe(
      "/backtest?ticker=AAPL&signal=connors_rsi2_long&eng=cerebro&filter=market&b=SPY&set.risk.atr_mult=3",
    );
    expect(backtestLink(form, "AAPL", "vectorized", null, config)).toContain("b=QQQ");
    expect(watchlistLink(form, config)).toBe(
      "/watchlist?w=us_large&signal=connors_rsi2_long&filter=market&b=QQQ&set.risk.atr_mult=3",
    );
  });

  it("offers the scanner's settings while the priority scores like the scanner, and drops them with another rule", () => {
    const scored =
      "w=us_large&signal=connors_rsi2_long&eng=vectorized&set.risk.atr_mult=3&set.scan.fresh_bars=5&set.scoring.trend_bonus=2&prio=score";
    const form = readPortfolioForm(new URLSearchParams(scored), config);
    expect(form.settings).toEqual({ risk: { atr_mult: 3 }, scan: { fresh_bars: 5 }, scoring: { trend_bonus: 2 } });
    expect(writePortfolioForm(form, config).toString()).toBe(new URLSearchParams(scored).toString());
    expect(portfolioSections(form, config)).toEqual(["risk", "backtest", "portfolio", "scoring", "trend", "scan"]);
    expect(portfolioBody(form)).toMatchObject({ priority: { name: "score", params: {} }, settings: form.settings });
    expect(backtestLink(form, "AAPL", "vectorized", null, config)).toBe(
      "/backtest?ticker=AAPL&signal=connors_rsi2_long&eng=vectorized&set.risk.atr_mult=3",
    );

    const momentum = choosePriority(form, "momentum", {}, config);
    expect(momentum).toMatchObject({ priority: "momentum", settings: { risk: { atr_mult: 3 } } });
    expect(portfolioSections(momentum, config)).toEqual(["risk", "backtest", "portfolio"]);
    expect(choosePriority(form, "score", {}, config).settings).toEqual(form.settings);
    expect(
      readPortfolioForm(new URLSearchParams(scored.replace("prio=score", "prio=momentum")), config).settings,
    ).toEqual({ risk: { atr_mult: 3 } });
  });

  it("round-trips the score's signal parameters while the priority scores like the scanner, and drops them with another rule", () => {
    const scored = "w=us_large&signal=connors_rsi2_long&eng=vectorized&prio=score&ss.donchian_breakout.period=55";
    const form = readPortfolioForm(new URLSearchParams(scored), config);
    expect(form.scoreSignalParams).toEqual({ donchian_breakout: { period: 55 } });
    expect(writePortfolioForm(form, config).toString()).toBe(new URLSearchParams(scored).toString());
    expect(portfolioBody(form)).toMatchObject({ score_signal_params: { donchian_breakout: { period: 55 } } });
    expect(priorityChanges(form, config)).toBe(2);
    expect(backtestLink(form, "AAPL", "vectorized", null, config)).toBe(
      "/backtest?ticker=AAPL&signal=connors_rsi2_long&eng=vectorized",
    );
    expect(resetPortfolio(form, config).scoreSignalParams).toEqual({});

    expect(choosePriority(form, "momentum", {}, config).scoreSignalParams).toEqual({});
    expect(choosePriority(form, "score", {}, config).scoreSignalParams).toEqual(form.scoreSignalParams);
    expect(
      readPortfolioForm(new URLSearchParams(scored.replace("prio=score", "prio=momentum")), config).scoreSignalParams,
    ).toEqual({});
  });

  it("keeps the score's signal parameters only for the signals it counts besides the traded one, and checks them", () => {
    const all = [...signals, { ...signals[0]!, name: "donchian_breakdown", direction: "short" as const }];
    const form = readPortfolioForm(new URLSearchParams("w=us_large&signal=connors_rsi2_long&prio=score"), config);
    expect(scoreSignals(form, all).map((signal) => signal.name)).toEqual(["donchian_breakout", "connors_rsi2_long"]);
    expect(scoreSignals({ signal: "" }, all)).toEqual(all);
    const params = {
      donchian_breakout: { period: 55 },
      connors_rsi2_long: { oversold: 5 },
      donchian_breakdown: { period: 30 },
    };
    expect(withCountedScoreSignals({ ...form, scoreSignalParams: params }, all).scoreSignalParams).toEqual({
      donchian_breakout: { period: 55 },
    });

    expect(hasScoreSignalProblems({ scoreSignalParams: { donchian_breakout: { period: 55 } } }, all)).toBe(false);
    expect(hasScoreSignalProblems({ scoreSignalParams: { donchian_breakout: { period: 1 } } }, all)).toBe(true);
    expect(hasScoreSignalProblems({ scoreSignalParams: { nope: { period: 5 } } }, all)).toBe(true);
  });

  it("leaves out the scan settings the score does not read", () => {
    const sections = pickSections(config.sections, ["scoring", "scan"]);
    expect(scoreExclusions(sections)).toEqual({ scoring: [], scan: ["min_score", "edge_horizon"] });
  });
});
