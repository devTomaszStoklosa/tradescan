import { describe, expect, it } from "vitest";

import {
  appliedRule,
  config,
  entryRules,
  exitRules,
  filterRules,
  makeMetrics,
  makeMonteCarlo,
  makePortfolioPin,
  makeRotationPin,
  makeRun,
  makeScanInputs,
  makeScorePin,
  priorityRules,
  signals,
  weightRules,
} from "../test/fixtures";
import { bestIndexes, metricValue, parameterRows, returnCurve } from "./compare";
import { decodeRuns, encodeRuns } from "./runsFile";

const differing = (rows: ReturnType<typeof parameterRows>) => rows.filter((row) => row.differs);

describe("parameterRows", () => {
  it("flags only the parameters that differ, with labels and units from the specs", () => {
    const base = makeRun(1);
    const changed = makeRun(2, { config: { ...base.config, atr_mult: 3 }, params: { ...base.params, oversold: 15 } });
    const rows = parameterRows([base, changed], config.sections, signals);

    expect(differing(rows)).toEqual([
      { key: "config.atr_mult", label: "Stop distance", unit: "ATR", values: ["2", "3"], differs: true },
      {
        key: "params.connors_rsi2_long.oversold",
        label: "connors_rsi2_long · Oversold level",
        unit: "",
        values: ["10", "15"],
        differs: true,
      },
    ]);
    expect(rows.find((row) => row.key === "ticker")).toMatchObject({ values: ["SPY", "SPY"], differs: false });
  });

  it("tells a pyramided run apart by its units and their distance", () => {
    const base = makeRun(1);
    const pyramided = makeRun(2, { config: { ...base.config, max_units: 4, add_every_atr: 1 } });
    expect(differing(parameterRows([base, pyramided], config.sections, signals))).toEqual([
      { key: "config.max_units", label: "Max units", unit: "", values: ["1", "4"], differs: true },
      { key: "config.add_every_atr", label: "Add every", unit: "ATR", values: ["0.5", "1"], differs: true },
    ]);
  });

  it("does not tell a run pinned before pyramiding apart from one that did not pyramid", () => {
    const stored = encodeRuns([makeRun(1)]).runs[0]!;
    const { max_units: _units, add_every_atr: _every, ...unpyramided } = stored.config;
    const [old] = decodeRuns({ version: 8, runs: [{ ...stored, config: unpyramided }] });
    const rows = parameterRows([old!, makeRun(2)], config.sections, signals);
    expect(differing(rows)).toEqual([]);
    expect(rows.find((row) => row.key === "config.max_units")).toMatchObject({ values: ["1", "1"] });
  });

  it("shows the Monte Carlo settings of runs that have one", () => {
    const base = makeRun(1);
    const rows = parameterRows(
      [base, makeRun(2, { monteCarlo: makeMonteCarlo({ seed: 7 }) })],
      config.sections,
      signals,
    );
    expect(differing(rows)).toEqual([
      { key: "monte_carlo.seed", label: "Monte Carlo · Random seed", unit: "", values: ["0", "7"], differs: true },
    ]);
    expect(rows.find((row) => row.key === "monte_carlo.ruin_drawdown_pct")).toMatchObject({
      label: "Monte Carlo · Ruin level",
      unit: "% drawdown",
    });
    const older = parameterRows([makeRun(1, { monteCarlo: null }), base], config.sections, signals);
    expect(older.find((row) => row.key === "monte_carlo.simulations")).toMatchObject({
      values: ["–", "1,000"],
      differs: true,
    });
    expect(parameterRows([makeRun(1, { monteCarlo: null })]).some((row) => row.key.startsWith("monte_carlo."))).toBe(
      false,
    );
  });

  it("falls back to readable names without specs", () => {
    const rows = parameterRows([makeRun(1)]);
    expect(rows.find((row) => row.key === "config.initial_equity")).toMatchObject({
      label: "Initial equity",
      values: ["100,000"],
    });
    expect(rows.find((row) => row.key === "params.connors_rsi2_long.trend_period")?.label).toBe(
      "connors_rsi2_long · Trend period",
    );
  });

  it("keeps parameters of different signals in separate rows", () => {
    const rsi = makeRun(1);
    const donchian = makeRun(2, { signal: "donchian_breakout", params: { period: 20 } });
    const rows = parameterRows([rsi, donchian], config.sections, signals);

    expect(rows.find((row) => row.key === "params.donchian_breakout.period")).toMatchObject({
      values: ["–", "20"],
      differs: true,
    });
    expect(rows.find((row) => row.key === "params.connors_rsi2_long.rsi_period")).toMatchObject({
      values: ["2", "–"],
      differs: true,
    });
    expect(rows.find((row) => row.key === "signal")?.differs).toBe(true);
  });

  it("shows the entry and exit rules with their parameters", () => {
    const limit = makeRun(2, {
      entry: appliedRule(entryRules[2]!, { offset_atr: 1 }),
      exits: [appliedRule(exitRules[1]!, { max_hold_bars: 5 })],
    });
    const rows = parameterRows([makeRun(1), limit], config.sections, signals, config);

    expect(differing(rows)).toEqual([
      { key: "entry", label: "Entry", unit: "", values: ["Next open", "Limit order"], differs: true },
      { key: "entry.limit.offset_atr", label: "Limit order · Offset", unit: "ATR", values: ["–", "1"], differs: true },
      {
        key: "entry.limit.valid_bars",
        label: "Limit order · Active for",
        unit: "bars",
        values: ["–", "1"],
        differs: true,
      },
      { key: "exits", label: "Exits", unit: "", values: ["Profit target, Time exit", "Time exit"], differs: true },
      { key: "exit.target.target_r", label: "Profit target · Distance", unit: "R", values: ["2", "–"], differs: true },
      {
        key: "exit.time.max_hold_bars",
        label: "Time exit · Hold for",
        unit: "bars",
        values: ["20", "5"],
        differs: true,
      },
    ]);
    expect(parameterRows([makeRun(1, { exits: [] })]).find((row) => row.key === "exits")?.values).toEqual([
      "stop only",
    ]);
  });

  it("shows the entry filters with their parameters, and the benchmark when a run compared one", () => {
    const market = makeRun(2, { filters: [appliedRule(filterRules[1]!, { period: 100 })], benchmark: "QQQ" });
    const rows = parameterRows([makeRun(1), market], config.sections, signals, config);

    expect(differing(rows)).toEqual([
      { key: "filters", label: "Filters", unit: "", values: ["none", "Market filter"], differs: true },
      { key: "benchmark", label: "Benchmark", unit: "", values: ["–", "QQQ"], differs: true },
      {
        key: "filter.market.period",
        label: "Market filter · Benchmark SMA",
        unit: "bars",
        values: ["–", "100"],
        differs: true,
      },
    ]);
    expect(parameterRows([makeRun(1)]).some((row) => row.key === "benchmark")).toBe(false);
  });

  it("shows what a portfolio tested, its limits and its priority rule next to a backtest", () => {
    const portfolio = makePortfolioPin(2, { portfolio: { max_positions: 5, max_exposure_pct: 150 } });
    const rows = parameterRows([makeRun(1), portfolio], config.sections, signals, config);
    const byKey = (key: string) => rows.find((row) => row.key === key);

    expect(rows.slice(0, 4).map((row) => row.key)).toEqual(["kind", "universe", "tickers", "ticker"]);
    expect(byKey("kind")).toMatchObject({ label: "Run", values: ["Backtest", "Portfolio"], differs: true });
    expect(byKey("ticker")).toMatchObject({ values: ["SPY", "–"], differs: true });
    expect(byKey("universe")).toMatchObject({ label: "Universe", values: ["–", "us_large"] });
    expect(byKey("tickers")).toMatchObject({ label: "Tickers", values: ["–", "2"] });
    expect(byKey("portfolio.max_positions")).toMatchObject({
      label: "Portfolio · Max positions",
      unit: "",
      values: ["–", "5"],
    });
    expect(byKey("portfolio.max_exposure_pct")).toMatchObject({
      label: "Portfolio · Max exposure",
      unit: "% of equity",
      values: ["–", "150"],
    });
    expect(byKey("priority")).toMatchObject({ label: "Priority", values: ["–", "Momentum"] });
    expect(byKey("priority.momentum.lookback")).toMatchObject({
      label: "Momentum · Lookback",
      unit: "bars",
      values: ["–", "252"],
    });
  });

  it("tells portfolio runs apart by their priority rules and limits", () => {
    const momentum = makePortfolioPin(1);
    const strength = makePortfolioPin(2, {
      priority: appliedRule(priorityRules[0]!),
      portfolio: { max_positions: 10, max_exposure_pct: 100 },
    });
    const rows = parameterRows([momentum, strength], config.sections, signals, config);

    expect(differing(rows)).toEqual([
      {
        key: "portfolio.max_positions",
        label: "Portfolio · Max positions",
        unit: "",
        values: ["5", "10"],
        differs: true,
      },
      { key: "priority", label: "Priority", unit: "", values: ["Momentum", "Relative strength"], differs: true },
      {
        key: "priority.momentum.lookback",
        label: "Momentum · Lookback",
        unit: "bars",
        values: ["252", "–"],
        differs: true,
      },
      { key: "priority.momentum.skip", label: "Momentum · Skip", unit: "bars", values: ["21", "–"], differs: true },
      {
        key: "priority.relative_strength.periods",
        label: "Relative strength · Lookbacks",
        unit: "bars",
        values: ["–", "63, 126, 189, 252"],
        differs: true,
      },
      {
        key: "priority.relative_strength.weights",
        label: "Relative strength · Weights",
        unit: "",
        values: ["–", "0.4, 0.2, 0.2, 0.2"],
        differs: true,
      },
    ]);
    expect(rows.find((row) => row.key === "kind")).toMatchObject({
      values: ["Portfolio", "Portfolio"],
      differs: false,
    });
  });

  it("tells score priority runs apart by the scanner settings and signal parameters they read", () => {
    const base = makeScorePin(1);
    const changed = makeScorePin(2, makeScanInputs({ trend_bonus: 2.5 }, 55));
    // The third run's momentum priority reads nothing of the scanner.
    const rows = parameterRows([base, changed, makePortfolioPin(3)], config.sections, signals, config);
    const WEIGHTS = "trend 1, momentum 1, breakout 1.5, mean_reversion 1, volume 1, pattern 0.5";

    expect(differing(rows).filter((row) => /^(scan|score_params)\./.test(row.key))).toEqual([
      {
        key: "scan.scoring.trend_bonus",
        label: "Scoring · Daily trend bonus",
        unit: "",
        values: ["1", "2.5", "–"],
        differs: true,
      },
      {
        key: "scan.scoring.family_weights",
        label: "Scoring · Family weights",
        unit: "",
        values: [WEIGHTS, WEIGHTS, "–"],
        differs: true,
      },
      {
        key: "scan.scoring.signal_weights",
        label: "Scoring · Signal weights",
        unit: "",
        values: ["none", "none", "–"],
        differs: true,
      },
      {
        key: "scan.trend.fast_period",
        label: "Trend & relative strength · Daily trend: fast SMA",
        unit: "bars",
        values: ["50", "50", "–"],
        differs: true,
      },
      {
        key: "scan.scan.fresh_bars",
        label: "Scan · Fresh within",
        unit: "bars",
        values: ["3", "3", "–"],
        differs: true,
      },
      {
        key: "score_params.donchian_breakout.period",
        label: "Score · donchian_breakout · Channel length",
        unit: "bars",
        values: ["20", "55", "–"],
        differs: true,
      },
    ]);
  });

  it("shows only the differing scanner inputs of score priority runs", () => {
    const rows = differing(
      parameterRows(
        [makeScorePin(1), makeScorePin(2, makeScanInputs({ trend_bonus: 2.5 }))],
        config.sections,
        signals,
        config,
      ),
    );
    expect(rows.map((row) => row.key)).toEqual(["scan.scoring.trend_bonus"]);
  });

  it("adds no portfolio rows when only backtest runs are compared", () => {
    const keys = parameterRows([makeRun(1), makeRun(2)], config.sections, signals, config).map((row) => row.key);
    expect(
      keys.filter(
        (key) =>
          ["kind", "universe", "tickers", "priority"].includes(key) ||
          /^(portfolio|priority|scan|score_params)\./.test(key),
      ),
    ).toEqual([]);
  });

  it("shows what a rotation tested, held and ranked by next to a backtest", () => {
    const rows = parameterRows([makeRun(1), makeRotationPin(2)], config.sections, signals, config);
    const byKey = (key: string) => rows.find((row) => row.key === key);

    expect(rows.slice(0, 5).map((row) => row.key)).toEqual(["kind", "universe", "tickers", "ticker", "signal"]);
    expect(byKey("kind")).toMatchObject({ values: ["Backtest", "Rotation"], differs: true });
    expect(byKey("universe")).toMatchObject({ values: ["–", "etf"] });
    expect(byKey("tickers")).toMatchObject({ values: ["–", "2"] });
    expect(byKey("signal")).toMatchObject({ values: ["connors_rsi2_long", "–"] });
    expect(byKey("rotation.holdings")).toMatchObject({ label: "Rotation · Holdings", unit: "", values: ["–", "3"] });
    expect(byKey("rotation.absolute_lookback")).toMatchObject({
      label: "Rotation · Absolute momentum",
      unit: "bars",
      values: ["–", "252"],
    });
    expect(byKey("rotation.rebalance")).toMatchObject({ label: "Rebalance", values: ["–", "monthly"] });
    expect(byKey("rotation.safe_asset")).toMatchObject({ label: "Safe asset", values: ["–", "TLT"] });
    expect(byKey("ranking")).toMatchObject({ label: "Ranking", values: ["–", "Momentum"] });
    expect(byKey("ranking.momentum.skip")).toMatchObject({
      label: "Momentum · Skip",
      unit: "bars",
      values: ["–", "21"],
    });
    expect(byKey("weighting")).toMatchObject({ label: "Weights", values: ["–", "Inverse volatility"] });
    expect(byKey("weighting.inverse_volatility.lookback")).toMatchObject({
      label: "Inverse volatility · Volatility lookback",
      unit: "bars",
      values: ["–", "63"],
    });
    expect(byKey("buy_hold_benchmark")).toMatchObject({ label: "Buy & hold benchmark", values: ["–", "SPY"] });
    expect(byKey("entry")).toMatchObject({ values: ["Next open", "–"] });
    expect(byKey("exits")?.values[1]).toBe("–");
    expect(byKey("filters")?.values[1]).toBe("–");
    expect(byKey("monte_carlo.simulations")?.values[1]).toBe("–");
  });

  it("tells rotation runs apart by their settings and rules, with cash for no safe asset", () => {
    const base = makeRotationPin(1);
    const changed = makeRotationPin(2, {
      rotation: { ...base.rotation, holdings: 5, rebalance: "weekly", safe_asset: null },
      weighting: appliedRule(weightRules[0]!),
    });
    const rows = parameterRows([base, changed], config.sections, signals, config);
    expect(differing(rows).map((row) => [row.key, row.values])).toEqual([
      ["rotation.holdings", ["3", "5"]],
      ["rotation.rebalance", ["monthly", "weekly"]],
      ["rotation.safe_asset", ["TLT", "cash"]],
      ["weighting", ["Inverse volatility", "Equal"]],
      ["weighting.inverse_volatility.lookback", ["63", "–"]],
    ]);
  });

  it("adds no rows of a signal's setup when only rotation runs are compared", () => {
    const keys = parameterRows([makeRotationPin(1), makeRotationPin(2)], config.sections, signals, config).map(
      (row) => row.key,
    );
    expect(keys.slice(0, 5)).toEqual(["kind", "universe", "tickers", "engine", "data"]);
    expect(
      keys.filter(
        (key) =>
          ["ticker", "signal", "filters", "benchmark", "entry", "exits", "priority"].includes(key) ||
          /^(monte_carlo|filter|entry|exit|params|portfolio|priority|scan|score_params)\./.test(key),
      ),
    ).toEqual([]);
  });

  it("adds no rotation rows when no rotation run is compared", () => {
    const keys = parameterRows([makeRun(1), makePortfolioPin(2)], config.sections, signals, config).map(
      (row) => row.key,
    );
    expect(
      keys.filter(
        (key) =>
          ["ranking", "weighting", "buy_hold_benchmark"].includes(key) || /^(rotation|ranking|weighting)\./.test(key),
      ),
    ).toEqual([]);
  });

  it("shows the data range so runs on different days are told apart", () => {
    const rows = parameterRows([makeRun(1), makeRun(2, { end: "2026-10-14" })]);
    expect(differing(rows).map((row) => row.key)).toEqual(["data"]);
  });
});

describe("metrics", () => {
  it("ranks an infinite profit factor first and skips missing values", () => {
    expect(metricValue(makeMetrics({ profit_factor: null, profit_factor_infinite: true }), "profit_factor")).toBe(
      Infinity,
    );
    expect(metricValue(makeMetrics({ sharpe: null }), "sharpe")).toBeNull();
  });

  it("marks the highest value, ties included, only when values differ", () => {
    expect(bestIndexes([-12, -5, null, -5])).toEqual(new Set([1, 3]));
    expect(bestIndexes([1, 1])).toEqual(new Set());
    expect(bestIndexes([3, null])).toEqual(new Set());
  });
});

describe("returnCurve", () => {
  it("rebases equity to % return since the first point", () => {
    expect(
      returnCurve([
        { time: "a", value: 200 },
        { time: "b", value: 250 },
      ]),
    ).toEqual([
      { time: "a", value: 0 },
      { time: "b", value: 25 },
    ]);
    expect(returnCurve([])).toEqual([]);
  });
});
