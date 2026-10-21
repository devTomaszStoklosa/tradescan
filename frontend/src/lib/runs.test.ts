import { describe, expect, it } from "vitest";

import {
  appliedRule,
  backtestForm,
  backtestResult,
  entryRules,
  exitRules,
  filterRules,
  makeMonteCarlo,
  makePortfolioPin,
  makePortfolioRun,
  makeRun,
  makeScanInputs,
  makeScorePin,
  portfolioForm,
  portfolioResult,
  priorityRules,
} from "../test/fixtures";
import {
  freeSlot,
  MAX_RUNS,
  mergeRuns,
  runKey,
  snapshotPortfolioRun,
  snapshotRun,
  toPinnedRun,
  type PinnedRun,
} from "./runs";
import {
  decodeRunRecord,
  decodeRuns,
  decodeSuggestingRun,
  encodeRuns,
  parseRunsFile,
  runRecord,
  RUNS_FILE_VERSION,
  suggestingRun,
} from "./runsFile";

describe("snapshotRun", () => {
  it("keeps one engine's result and reopens with only that engine", () => {
    const snapshot = snapshotRun(backtestResult, "vectorized", { ...backtestForm, engines: ["vectorized", "cerebro"] });
    expect(snapshot).toMatchObject({ ticker: "SPY", engine: "vectorized", start: "2016-01-04", end: "2026-10-13" });
    expect(snapshot?.form.engines).toEqual(["vectorized"]);
    expect(snapshot?.metrics.trades).toBe(42);
    expect(snapshot?.entry.name).toBe("next_open");
    expect(snapshot?.exits.map((exit) => exit.name)).toEqual(["target", "time"]);
    expect(snapshot).not.toHaveProperty("trades");
  });

  it("returns null for an engine that did not run", () => {
    expect(snapshotRun(backtestResult, "cerebro", backtestForm)).toBeNull();
  });

  it("keeps the in-sample and out-of-sample results with their dates", () => {
    const snapshot = snapshotRun(backtestResult, "vectorized", backtestForm);
    expect(snapshot?.split).toMatchObject({
      oos_pct: 30,
      out_of_sample_start: "2023-07-03",
      in_sample: { sharpe: 1.1 },
      out_of_sample: { sharpe: 0.2 },
    });
    const short = {
      ...backtestResult,
      split: null,
      runs: backtestResult.runs.map((run) => ({ ...run, in_sample: null, out_of_sample: null })),
    };
    expect(snapshotRun(short, "vectorized", backtestForm)?.split).toBeNull();
  });

  it("keeps the Monte Carlo of the run's trades", () => {
    expect(snapshotRun(backtestResult, "vectorized", backtestForm)?.monteCarlo).toEqual(makeMonteCarlo());
    const few = { ...backtestResult, runs: backtestResult.runs.map((run) => ({ ...run, monte_carlo: null })) };
    expect(snapshotRun(few, "vectorized", backtestForm)?.monteCarlo).toBeNull();
  });
});

describe("snapshotPortfolioRun", () => {
  it("keeps one engine's portfolio result and reopens with only that engine", () => {
    const result = { ...portfolioResult, runs: [makePortfolioRun("vectorized"), makePortfolioRun("cerebro")] };
    const snapshot = snapshotPortfolioRun(result, "cerebro", { ...portfolioForm, engines: ["vectorized", "cerebro"] });
    expect(snapshot).toMatchObject({
      kind: "portfolio",
      universe: "us_large",
      tickers: ["AAPL", "MSFT"],
      missing: ["TSLA"],
      engine: "cerebro",
      portfolio: { max_positions: 5, max_exposure_pct: 100 },
      priority: { name: "momentum", params: { lookback: 252, skip: 21 } },
      metrics: { trades: 118 },
      monteCarlo: null,
    });
    expect(snapshot?.form).toMatchObject({
      engines: ["cerebro"],
      priority: "momentum",
      universe: { watchlist: "us_large" },
    });
    expect(snapshot?.scan).toBeNull();
    expect(snapshot).not.toHaveProperty("trades");
    expect(snapshot).not.toHaveProperty("positions");
  });

  it("keeps the stats and metrics of both periods with the split's dates", () => {
    const snapshot = snapshotPortfolioRun(portfolioResult, "vectorized", portfolioForm);
    expect(snapshot?.stats).toMatchObject({
      full: { orders: 120 },
      in_sample: { orders: 82 },
      out_of_sample: { orders: 38 },
    });
    expect(snapshot?.split).toMatchObject({
      out_of_sample_start: "2023-07-03",
      in_sample: { sharpe: 1.1 },
      out_of_sample: { sharpe: 0.3 },
    });

    const short = {
      ...portfolioResult,
      split: null,
      runs: [makePortfolioRun("vectorized", { in_sample: null, out_of_sample: null })],
    };
    expect(snapshotPortfolioRun(short, "vectorized", portfolioForm)).toMatchObject({
      split: null,
      stats: { in_sample: null, out_of_sample: null },
    });
  });

  it("returns null for an engine that did not run", () => {
    expect(snapshotPortfolioRun(portfolioResult, "cerebro", portfolioForm)).toBeNull();
  });

  it("names a pinned portfolio after its universe", () => {
    expect(makePortfolioPin(1).name).toBe("us_large connors_rsi2_long");
  });
});

describe("runKey", () => {
  it("ignores names, slots and key order but not parameters or the data range", () => {
    const run = makeRun(1);
    expect(runKey(makeRun(2, {}, { name: "other" }))).toBe(runKey(run));
    expect(runKey(makeRun(1, { params: { oversold: 10, trend_period: 200, rsi_period: 2 } }))).toBe(runKey(run));
    expect(runKey(makeRun(1, { params: { ...run.params, oversold: 15 } }))).not.toBe(runKey(run));
    expect(runKey(makeRun(1, { config: { ...run.config, atr_mult: 3 } }))).not.toBe(runKey(run));
    expect(runKey(makeRun(1, { end: "2026-10-14" }))).not.toBe(runKey(run));
    expect(runKey(makeRun(1, { config: { ...run.config, oos_pct: 20 } }))).not.toBe(runKey(run));
  });

  it("tells runs apart by their entry and exit rules", () => {
    const run = makeRun(1);
    expect(runKey(makeRun(1, { entry: appliedRule(entryRules[2]!) }))).not.toBe(runKey(run));
    expect(runKey(makeRun(1, { exits: [appliedRule(exitRules[0]!, { target_r: 3 }), run.exits[1]!] }))).not.toBe(
      runKey(run),
    );
    expect(runKey(makeRun(1, { exits: [run.exits[0]!] }))).not.toBe(runKey(run));
    expect(runKey(makeRun(1, { entry: { ...run.entry, description: "other words" } }))).toBe(runKey(run));
  });

  it("tells runs apart by their entry filters and benchmark", () => {
    const run = makeRun(1, { filters: [appliedRule(filterRules[1]!)], benchmark: "SPY" });
    expect(runKey(run)).not.toBe(runKey(makeRun(1)));
    expect(runKey(makeRun(1, { filters: [appliedRule(filterRules[1]!, { period: 100 })], benchmark: "SPY" }))).not.toBe(
      runKey(run),
    );
    expect(runKey(makeRun(1, { filters: run.filters, benchmark: "QQQ" }))).not.toBe(runKey(run));
  });

  it("tells runs apart by their Monte Carlo settings but not by its results", () => {
    const run = makeRun(1);
    expect(runKey(makeRun(1, { monteCarlo: makeMonteCarlo({ seed: 1 }) }))).not.toBe(runKey(run));
    expect(runKey(makeRun(1, { monteCarlo: makeMonteCarlo({ simulations: 5000 }) }))).not.toBe(runKey(run));
    expect(runKey(makeRun(1, { monteCarlo: makeMonteCarlo({ ruin_drawdown_pct: 30 }) }))).not.toBe(runKey(run));
    expect(runKey(makeRun(1, { monteCarlo: makeMonteCarlo({ methods: [] }) }))).toBe(runKey(run));
  });
});

describe("runKey of portfolio runs", () => {
  it("tells portfolio runs apart by their limits, priority rule and members", () => {
    const run = makePortfolioPin(1);
    expect(runKey(makePortfolioPin(2, {}, { name: "other" }))).toBe(runKey(run));
    expect(runKey(makePortfolioPin(1, { portfolio: { ...run.portfolio, max_positions: 10 } }))).not.toBe(runKey(run));
    expect(runKey(makePortfolioPin(1, { portfolio: { ...run.portfolio, max_exposure_pct: 150 } }))).not.toBe(
      runKey(run),
    );
    expect(runKey(makePortfolioPin(1, { priority: appliedRule(priorityRules[1]!, { skip: 0 }) }))).not.toBe(
      runKey(run),
    );
    expect(runKey(makePortfolioPin(1, { priority: appliedRule(priorityRules[0]!) }))).not.toBe(runKey(run));
    expect(runKey(makePortfolioPin(1, { tickers: ["AAPL", "MSFT", "NVDA"] }))).not.toBe(runKey(run));
    expect(runKey(makePortfolioPin(1, { tickers: ["MSFT", "AAPL"] }))).toBe(runKey(run));
    expect(runKey(makePortfolioPin(1, { universe: "custom" }))).not.toBe(runKey(run));
    expect(runKey(makePortfolioPin(1, { params: { ...run.params, oversold: 15 } }))).not.toBe(runKey(run));
  });

  it("tells score priority runs apart by what they read of the scanner, in any key order", () => {
    const run = makeScorePin(1);
    expect(runKey(makeScorePin(1, makeScanInputs({ trend_bonus: 2.5 })))).not.toBe(runKey(run));
    expect(runKey(makeScorePin(1, makeScanInputs({}, 55)))).not.toBe(runKey(run));
    expect(runKey(makePortfolioPin(1, { priority: run.priority, scan: null }))).not.toBe(runKey(run));
    const { scoring, trend, scan } = run.scan!.settings;
    const reordered = {
      ...run.scan!,
      settings: { scan: scan!, trend: trend!, scoring: Object.fromEntries(Object.entries(scoring!).reverse()) },
    };
    expect(runKey(makeScorePin(1, reordered))).toBe(runKey(run));
  });

  it("never equals the key of a backtest run", () => {
    const portfolio = makePortfolioPin(1);
    const backtest = makeRun(1, {
      ticker: "us_large",
      filters: portfolio.filters,
      benchmark: portfolio.benchmark,
      monteCarlo: null,
    });
    expect(runKey(portfolio)).not.toBe(runKey(backtest));
  });
});

describe("mergeRuns", () => {
  it("pins backtest and portfolio runs next to each other", () => {
    const result = mergeRuns([makeRun(1)], [makePortfolioPin(1), makePortfolioPin(4)]);
    expect(result.runs.map((run) => [run.kind, run.slot])).toEqual([
      ["backtest", 1],
      ["portfolio", 2],
    ]);
    expect(result).toMatchObject({ added: 1, duplicates: 1 });
  });

  it("assigns the lowest free slot and skips runs already pinned", () => {
    const first = makeRun(1);
    const result = mergeRuns(
      [first],
      [toPinnedRun(makeRun(1, { config: { ...first.config, atr_mult: 3 } })), toPinnedRun(first)],
    );
    expect(result.runs.map((run) => run.slot)).toEqual([1, 2]);
    expect(result).toMatchObject({ added: 1, duplicates: 1, overflow: 0 });
  });

  it("keeps a free slot, re-slots a taken one and replaces a taken id", () => {
    const current = [makeRun(3)];
    const incoming = [makeRun(5, { end: "2026-01-02" }), makeRun(3, { end: "2026-01-05" }, { id: "run-3" })];
    const { runs } = mergeRuns(current, incoming);
    expect(runs.map((run) => run.slot)).toEqual([1, 3, 5]);
    expect(new Set(runs.map((run) => run.id)).size).toBe(3);
  });

  it(`stops at ${MAX_RUNS} runs`, () => {
    const incoming = Array.from({ length: MAX_RUNS + 2 }, (_, index) =>
      makeRun(1, { end: `2026-01-${String(index + 1).padStart(2, "0")}` }),
    );
    const result = mergeRuns([], incoming);
    expect(result.runs).toHaveLength(MAX_RUNS);
    expect(result.overflow).toBe(2);
    expect(freeSlot(result.runs)).toBeNull();
  });
});

describe("runs file", () => {
  it("round-trips runs with equity rounded to cents", () => {
    const run = makeRun(2, {}, { name: "stop 3 ATR", hidden: true });
    const file = encodeRuns([run]);
    expect(file.version).toBe(RUNS_FILE_VERSION);
    expect(file.runs[0]?.equity.value).toEqual([100000, 105000.12, 112500]);
    const [decoded] = parseRunsFile(JSON.stringify(file));
    expect(decoded).toEqual({
      ...run,
      equity: run.equity.map((point) => ({ ...point, value: Math.round(point.value * 100) / 100 })),
    });
  });

  it("upgrades version 1 runs, whose target and time exit were settings", () => {
    const { entry: _entry, exits: _exits, ...current } = encodeRuns([makeRun(1)]).runs[0]!;
    const { entry: _a, entryParams: _b, exits: _c, exitParams: _d, ...oldForm } = current.form;
    const v1 = {
      ...current,
      config: { ...current.config, target_r: 3, max_hold_bars: 20 },
      form: { ...oldForm, settings: { backtest: { target_r: 3 } } },
    };
    const [run] = decodeRuns({ version: 1, runs: [v1] });

    expect(run!.config).not.toHaveProperty("target_r");
    expect(run!.config).not.toHaveProperty("max_hold_bars");
    expect(run!.entry).toEqual(appliedRule(entryRules[0]!));
    expect(run!.exits).toEqual([appliedRule(exitRules[0]!, { target_r: 3 }), appliedRule(exitRules[1]!)]);
    expect(run!.form).toMatchObject({
      settings: {},
      entry: "next_open",
      entryParams: {},
      exits: ["target", "time"],
      exitParams: { target: { target_r: 3 } },
    });
    expect(runKey(run!)).toBe(
      runKey(
        makeRun(1, {
          exits: [appliedRule(exitRules[0]!, { target_r: 3 }), appliedRule(exitRules[1]!)],
          monteCarlo: null,
        }),
      ),
    );
  });

  it("upgrades version 2 runs, which have no out-of-sample results", () => {
    const { split: _split, ...current } = encodeRuns([makeRun(1)]).runs[0]!;
    const { oos_pct: _oos, ...config } = current.config;
    const [run] = decodeRuns({ version: 2, runs: [{ ...current, config }] });
    expect(run!.split).toBeNull();
    expect(run!.config).not.toHaveProperty("oos_pct");
    expect(run!.metrics).toEqual(makeRun(1).metrics);
  });

  it("upgrades version 3 runs, which had no entry filters", () => {
    const { filters: _filters, benchmark: _benchmark, ...current } = encodeRuns([makeRun(1)]).runs[0]!;
    const { filters: _a, filterParams: _b, benchmark: _c, ...form } = current.form;
    const [run] = decodeRuns({ version: 3, runs: [{ ...current, form }] });
    expect(run).toMatchObject({ filters: [], benchmark: null, form: { filters: [], filterParams: {}, benchmark: "" } });
    expect(runKey(run!)).toBe(runKey(makeRun(1, { monteCarlo: null })));
  });

  it("upgrades version 4 runs, which have no Monte Carlo", () => {
    const { monteCarlo: _monteCarlo, ...current } = encodeRuns([makeRun(1)]).runs[0]!;
    const [run] = decodeRuns({ version: 4, runs: [current] });
    expect(run!.monteCarlo).toBeNull();
    expect(runKey(run!)).toBe(runKey(makeRun(1, { monteCarlo: null })));
  });

  it("upgrades version 5 runs, which were all backtests of one ticker", () => {
    const { kind: _kind, ...current } = encodeRuns([makeRun(1)]).runs[0]!;
    const [run] = decodeRuns({ version: 5, runs: [current] });
    expect(run).toMatchObject({ kind: "backtest", ticker: "SPY" });
    expect(runKey(run!)).toBe(runKey(makeRun(1)));
  });

  it("upgrades version 6 portfolio runs, whose score counted the other signals with their defaults", () => {
    const pins = [makeRun(1), makePortfolioPin(2)];
    const old = encodeRuns(pins).runs.map((run) =>
      run.kind === "portfolio" ? { ...run, form: { ...run.form, scoreSignalParams: undefined } } : run,
    );
    const runs = parseRunsFile(JSON.stringify({ version: 6, runs: old }));
    expect(runs[1]).toMatchObject({ kind: "portfolio", form: { scoreSignalParams: {} } });
    expect(runs.map(runKey)).toEqual(pins.map(runKey));
    expect(() => parseRunsFile(JSON.stringify({ version: RUNS_FILE_VERSION, runs: old }))).toThrow(
      'Run 2 has an invalid "form"',
    );
  });

  it("upgrades version 7 portfolio runs, whose result did not report what the score read of the scanner", () => {
    const pins = [makeRun(1), makeScorePin(2)];
    const old = encodeRuns(pins).runs.map((run) => (run.kind === "portfolio" ? { ...run, scan: undefined } : run));
    const runs = parseRunsFile(JSON.stringify({ version: 7, runs: old }));
    expect(runs[0]).not.toHaveProperty("scan");
    expect(runs[1]).toMatchObject({ kind: "portfolio", priority: { name: "score" }, scan: null });
    expect(() => parseRunsFile(JSON.stringify({ version: RUNS_FILE_VERSION, runs: old }))).toThrow(
      'Run 2 has an invalid "scan"',
    );
  });

  it("upgrades version 8 runs pinned before pyramiding, which held one unit", () => {
    const pins = [makeRun(1), makePortfolioPin(2)];
    const old = encodeRuns(pins).runs.map((run) => {
      const { max_units: _units, add_every_atr: _every, ...config } = run.config;
      return { ...run, config };
    });
    const runs = parseRunsFile(JSON.stringify({ version: 8, runs: old }));
    for (const run of runs) expect(run.config).toMatchObject({ max_units: 1, add_every_atr: 0.5 });
    expect(runs.map(runKey)).toEqual(pins.map(runKey));
  });

  it("keeps the pyramiding of version 8 runs pinned after it came", () => {
    const pin = makeRun(1, { config: { ...makeRun(1).config, max_units: 3, add_every_atr: 1 } });
    const [run] = parseRunsFile(JSON.stringify({ version: 8, runs: encodeRuns([pin]).runs }));
    expect(run!.config).toMatchObject({ max_units: 3, add_every_atr: 1 });
  });

  it("round-trips portfolio runs next to backtest runs", () => {
    const runs = [makeRun(1), makePortfolioPin(2, {}, { name: "top 5 by momentum" }), makeScorePin(3)];
    const decoded = parseRunsFile(JSON.stringify(encodeRuns(runs)));
    expect(decoded).toEqual(
      runs.map((run) => ({
        ...run,
        equity: run.equity.map((point) => ({ ...point, value: Math.round(point.value * 100) / 100 })),
      })),
    );
    expect(decoded.map(runKey)).toEqual(runs.map(runKey));
  });

  it("drops fields it does not know", () => {
    const file = encodeRuns([makeRun(1)]);
    const [decoded] = decodeRuns({ ...file, runs: [{ ...file.runs[0], extra: "x" }] });
    expect(decoded).not.toHaveProperty("extra");
  });

  it.each([
    ["not JSON", "{", "The file is not valid JSON"],
    ["another file", JSON.stringify({ hello: 1 }), "This is not a tradescan runs file"],
    ["a newer version", JSON.stringify({ version: 99, runs: [] }), "Unsupported runs file version: 99"],
    [
      "a run without metrics",
      JSON.stringify({ version: 2, runs: [{ ...encodeRuns([makeRun(1)]).runs[0], metrics: null }] }),
      'Run 1 has an invalid "metrics"',
    ],
    [
      "a slot out of range",
      JSON.stringify({ version: 2, runs: [{ ...encodeRuns([makeRun(1)]).runs[0], slot: 9 }] }),
      'Run 1 has an invalid "slot"',
    ],
    [
      "uneven equity arrays",
      JSON.stringify({
        version: 2,
        runs: [{ ...encodeRuns([makeRun(1)]).runs[0], equity: { time: ["2020-01-01"], value: [] } }],
      }),
      'Run 1 has an invalid "equity"',
    ],
    [
      "a split without metrics",
      JSON.stringify({
        version: 3,
        runs: [{ ...encodeRuns([makeRun(1)]).runs[0], split: { ...makeRun(1).split, out_of_sample: null } }],
      }),
      'Run 1 has an invalid "split"',
    ],
    [
      "a Monte Carlo without methods",
      JSON.stringify({
        version: RUNS_FILE_VERSION,
        runs: [{ ...encodeRuns([makeRun(1)]).runs[0], monteCarlo: { ...makeMonteCarlo(), methods: null } }],
      }),
      'Run 1 has an invalid "monteCarlo"',
    ],
    [
      "a Monte Carlo method without percentiles",
      JSON.stringify({
        version: RUNS_FILE_VERSION,
        runs: [
          {
            ...encodeRuns([makeRun(1)]).runs[0],
            monteCarlo: {
              ...makeMonteCarlo(),
              methods: [{ ...makeMonteCarlo().methods[0], max_drawdown_pct: { p5: 1 } }],
            },
          },
        ],
      }),
      'Run 1 has an invalid "monteCarlo"',
    ],
    [
      "a bad rule",
      JSON.stringify({ version: 2, runs: [{ ...encodeRuns([makeRun(1)]).runs[0], exits: [{ name: "target" }] }] }),
      'Run 1 has an invalid "exits"',
    ],
    [
      "an unknown kind",
      JSON.stringify({ version: RUNS_FILE_VERSION, runs: [{ ...encodeRuns([makeRun(1)]).runs[0], kind: "rotation" }] }),
      'Run 1 has an invalid "kind"',
    ],
    [
      "a run without a kind",
      JSON.stringify({ version: RUNS_FILE_VERSION, runs: [{ ...encodeRuns([makeRun(1)]).runs[0], kind: undefined }] }),
      'Run 1 has an invalid "kind"',
    ],
    [
      "a portfolio run without its ticker list",
      JSON.stringify({
        version: RUNS_FILE_VERSION,
        runs: [{ ...encodeRuns([makePortfolioPin(1)]).runs[0], tickers: "AAPL,MSFT" }],
      }),
      'Run 1 has an invalid "tickers"',
    ],
    [
      "a portfolio run with bad stats",
      JSON.stringify({
        version: RUNS_FILE_VERSION,
        runs: [
          {
            ...encodeRuns([makePortfolioPin(1)]).runs[0],
            stats: { ...makePortfolioPin(1).stats, full: { orders: 120 } },
          },
        ],
      }),
      'Run 1 has an invalid "stats"',
    ],
    [
      "a portfolio run without its limits",
      JSON.stringify({
        version: RUNS_FILE_VERSION,
        runs: [{ ...encodeRuns([makePortfolioPin(1)]).runs[0], portfolio: { max_positions: 5 } }],
      }),
      'Run 1 has an invalid "portfolio"',
    ],
    [
      "a portfolio run with bad scan inputs",
      JSON.stringify({
        version: RUNS_FILE_VERSION,
        runs: [
          {
            ...encodeRuns([makeScorePin(1)]).runs[0],
            scan: { settings: { scan: { fresh_bars: "3" } }, signal_params: {} },
          },
        ],
      }),
      'Run 1 has an invalid "scan"',
    ],
    [
      "a portfolio run with a backtest form",
      JSON.stringify({
        version: RUNS_FILE_VERSION,
        runs: [{ ...encodeRuns([makePortfolioPin(1)]).runs[0], form: backtestForm }],
      }),
      'Run 1 has an invalid "form"',
    ],
    [
      "a backtest run with a portfolio form",
      JSON.stringify({
        version: RUNS_FILE_VERSION,
        runs: [{ ...encodeRuns([makeRun(1)]).runs[0], form: portfolioForm }],
      }),
      'Run 1 has an invalid "form"',
    ],
    [
      "a bad form value",
      JSON.stringify({
        version: 2,
        runs: [
          { ...encodeRuns([makeRun(1)]).runs[0], form: { ...backtestForm, settings: { risk: { atr_mult: "3" } } } },
        ],
      }),
      'Run 1 has an invalid "form"',
    ],
  ])("rejects %s", (_, content, message) => {
    expect(() => parseRunsFile(content)).toThrow(message);
  });
});

describe("server records of runs", () => {
  const rounded = (run: PinnedRun) => ({
    ...run,
    equity: run.equity.map((point) => ({ ...point, value: Math.round(point.value * 100) / 100 })),
  });

  it("keeps the pin in its own fields and the rest as the snapshot", () => {
    const run = makePortfolioPin(3, {}, { name: "top 5", hidden: true });
    const record = runRecord(run);
    expect(record).toMatchObject({
      id: run.id,
      slot: 3,
      name: "top 5",
      hidden: true,
      pinned_at: run.pinnedAt,
      format: RUNS_FILE_VERSION,
    });
    for (const field of ["id", "slot", "name", "hidden", "pinnedAt"]) expect(record.snapshot).not.toHaveProperty(field);
    expect(record.snapshot).toMatchObject({ kind: "portfolio", universe: "us_large" });
    expect(decodeRunRecord(JSON.parse(JSON.stringify(record)) as typeof record)).toEqual(rounded(run));
  });

  it("upgrades a record written in an older version", () => {
    const { kind: _kind, ...snapshot } = runRecord(makeRun(1)).snapshot;
    const run = decodeRunRecord({ ...runRecord(makeRun(1)), format: 5, snapshot });
    expect(run).toMatchObject({ kind: "backtest", ticker: "SPY" });
    expect(() => decodeRunRecord({ ...runRecord(makeRun(1)), format: 99 })).toThrow(
      "Unsupported runs file version: 99",
    );
    expect(() => decodeRunRecord({ ...runRecord(makeRun(1)), slot: 0 }, 2)).toThrow('Run 3 has an invalid "slot"');
  });

  it("copies the whole run, its name included, for the trade it suggested", () => {
    const run = makeRun(2, {}, { name: "RSI2 15" });
    const copy = suggestingRun(run);
    expect(copy.format).toBe(RUNS_FILE_VERSION);
    expect(copy.snapshot).toMatchObject({ id: run.id, slot: 2, name: "RSI2 15" });
    expect(decodeSuggestingRun(JSON.parse(JSON.stringify(copy)) as typeof copy)).toEqual(rounded(run));
  });
});
