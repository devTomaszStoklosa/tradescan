import { describe, expect, it } from "vitest";

import type { JournalTradeOut } from "../api/client";
import { makePortfolioPin, makeRun } from "../test/fixtures";
import { newTradeForm, suggestedBy, today, tradeBody, tradeFormOf } from "./journal";
import { RUNS_FILE_VERSION, suggestingRun } from "./runsFile";

const NOW = new Date(2026, 9, 18, 23, 30); // late evening: still the 18th in the browser's time zone

describe("journal form", () => {
  it("starts a trade today, long, without a run", () => {
    expect(today(NOW)).toBe("2026-10-18");
    expect(newTradeForm(undefined, NOW)).toMatchObject({ ticker: "", direction: "long", opened: "2026-10-18", run: null, closed: "" });
  });

  it("starts a trade from a pinned run with its ticker, direction and a copy of the run", () => {
    const run = makeRun(1, { direction: "short" }, { name: "baseline" });
    const form = newTradeForm(run, NOW);
    expect(form).toMatchObject({ ticker: "SPY", direction: "short" });
    expect(form.run).toEqual(suggestingRun(run));
    // A portfolio tested a universe, so the ticker is left to fill in.
    expect(newTradeForm(makePortfolioPin(2), NOW).ticker).toBe("");
  });

  it("waits for the ticker, the entry and the quantity before it makes a request", () => {
    const form = { ...newTradeForm(undefined, NOW), ticker: " pko.wa ", entryPrice: 50.5 };
    expect(tradeBody(form)).toBeNull();
    expect(tradeBody({ ...form, quantity: 10, notes: "  breakout  " })).toEqual({
      ticker: "PKO.WA",
      direction: "long",
      opened: "2026-10-18",
      entry_price: 50.5,
      quantity: 10,
      stop: null,
      closed: null,
      exit_price: null,
      fees: 0,
      notes: "breakout",
      run: null,
    });
    expect(tradeBody({ ...form, quantity: 10, opened: "" })).toBeNull();
  });

  it("edits a trade with everything it was logged with", () => {
    const run = suggestingRun(makeRun(1));
    const trade = {
      id: 3,
      ticker: "SPY",
      direction: "long",
      opened: "2026-03-02",
      entry_price: 500,
      quantity: 2,
      stop: 490,
      closed: "2026-03-20",
      exit_price: 530,
      fees: 0,
      notes: "Target",
      run,
    } as JournalTradeOut;
    const form = tradeFormOf(trade);
    expect(form).toMatchObject({ stop: 490, closed: "2026-03-20", exitPrice: 530, fees: null, run });
    expect(tradeBody(form)).toMatchObject({ entry_price: 500, closed: "2026-03-20", exit_price: 530, fees: 0, run });
  });

  it("reads the run a trade keeps, or says why it cannot", () => {
    const run = makeRun(1, {}, { name: "baseline" });
    expect(suggestedBy(suggestingRun(run))).toMatchObject({ run: { name: "baseline", ticker: "SPY" } });
    expect(suggestedBy({ format: RUNS_FILE_VERSION, snapshot: { kind: "backtest" } })).toEqual({ problem: 'Run 1 has an invalid "id"' });
  });
});
