import { describe, expect, it } from "vitest";

import { config } from "../test/fixtures";
import { toCsv } from "./csv";
import { DASH, fmtPct, fmtPrice, fmtSigned, fmtSize, tone } from "./format";
import { backtestBody, edgeBody, readBacktestForm, readScanForm, scanBody, writeBacktestForm, writeScanForm } from "./params";
import { compareValues } from "./useSortable";

describe("format", () => {
  it("formats missing values as a dash", () => {
    expect(fmtPrice(null)).toBe(DASH);
    expect(fmtPct(Number.NaN)).toBe(DASH);
  });

  it("adapts price decimals and signs", () => {
    expect(fmtPrice(1234.5)).toBe("1,234.50");
    expect(fmtPrice(0.1234)).toBe("0.1234");
    expect(fmtPct(2.345, 1, true)).toBe("+2.3%");
    expect(fmtSigned(-1.5)).toBe("-1.50");
    expect(fmtSigned(-0.001)).toBe("0.00");
    expect(fmtSize(250)).toBe("250");
    expect(fmtSize(0.0333)).toBe("0.0333");
    expect(tone(1)).toBe("text-up");
    expect(tone(-1)).toBe("text-down");
    expect(tone(null)).toBe("");
  });
});

describe("csv", () => {
  it("quotes fields that need it", () => {
    expect(toCsv([{ a: "x,y", b: 'say "hi"', c: null }])).toBe('a,b,c\n"x,y","say ""hi""",');
  });
});

describe("sorting", () => {
  it("puts missing values last in both directions", () => {
    expect([3, null, 1].sort((a, b) => compareValues(a, b, "asc"))).toEqual([1, 3, null]);
    expect([3, null, 1].sort((a, b) => compareValues(a, b, "desc"))).toEqual([3, 1, null]);
  });
});

describe("url params", () => {
  it("round-trips the scan form and builds the request", () => {
    const params = writeScanForm({
      universe: { watchlist: "", tickers: "aapl msft; pko.wa" },
      direction: "long",
      families: ["breakout", "trend"],
      period: "2y",
      benchmark: "qqq",
      settings: { scan: { fresh_bars: 5 }, scoring: { family_weights: { breakout: 2 } } },
      signalParams: { donchian_breakout: { period: 30 } },
    });
    expect(params.toString()).toBe(
      "t=AAPL%2CMSFT%2CPKO.WA&dir=long&fam=breakout%2Ctrend&p=2y&b=QQQ&set.scan.fresh_bars=5" +
        "&set.scoring.family_weights.breakout=2&sig.donchian_breakout.period=30",
    );
    const form = readScanForm(params);
    expect(scanBody(form)).toEqual({
      tickers: ["AAPL", "MSFT", "PKO.WA"],
      families: ["breakout", "trend"],
      direction: "long",
      period: "2y",
      benchmark: "QQQ",
      settings: { scan: { fresh_bars: 5 }, scoring: { family_weights: { breakout: 2 } } },
      signal_params: { donchian_breakout: { period: 30 } },
    });
  });

  it("keeps an unchanged scan URL short", () => {
    expect(writeScanForm(readScanForm(new URLSearchParams("w=etf"))).toString()).toBe("w=etf");
  });

  it("returns no request without a universe or with invalid input", () => {
    expect(scanBody(readScanForm(new URLSearchParams()))).toBeNull();
    expect(
      edgeBody({ universe: { watchlist: "etf", tickers: "" }, direction: "both", families: [], horizons: "x", minEvents: 0, period: "", signalParams: {} }),
    ).toBeNull();
    expect(backtestBody(readBacktestForm(new URLSearchParams("ticker=spy"), config))).toBeNull();
  });

  it("ignores unknown families and directions from the URL", () => {
    const form = readScanForm(new URLSearchParams("w=etf&dir=sideways&fam=trend,bogus"));
    expect(form.direction).toBe("both");
    expect(form.families).toEqual(["trend"]);
  });

  it("builds a backtest request with only the selected signal's parameters", () => {
    const url = "ticker=spy&signal=golden_cross&eng=vectorized,cerebro&set.risk.atr_mult=2.5&sig.golden_cross.fast=20&sig.death_cross.fast=5";
    const form = readBacktestForm(new URLSearchParams(url), config);
    expect(backtestBody(form)).toEqual({
      ticker: "SPY",
      signal: "golden_cross",
      engines: ["vectorized", "cerebro"],
      period: null,
      params: { fast: 20 },
      settings: { risk: { atr_mult: 2.5 } },
      entry: { name: "next_open", params: {} },
      exits: [
        { name: "target", params: {} },
        { name: "time", params: {} },
      ],
    });
    expect(writeBacktestForm(form, config).toString()).toBe(
      "ticker=SPY&signal=golden_cross&eng=vectorized%2Ccerebro&set.risk.atr_mult=2.5&sig.golden_cross.fast=20",
    );
  });

  it("keeps trade rules in the URL only when they differ from the defaults", () => {
    const url =
      "ticker=SPY&signal=golden_cross&entry=limit&exit=time&en.limit.offset_atr=1&en.stop.offset_atr=2&ex.time.max_hold_bars=5&ex.target.target_r=3";
    const form = readBacktestForm(new URLSearchParams(url), config);
    expect(form).toMatchObject({ entry: "limit", entryParams: { offset_atr: 1 }, exits: ["time"], exitParams: { time: { max_hold_bars: 5 } } });
    expect(backtestBody(form)).toMatchObject({ entry: { name: "limit", params: { offset_atr: 1 } }, exits: [{ name: "time", params: { max_hold_bars: 5 } }] });
    expect(writeBacktestForm(form, config).toString()).toBe(
      "ticker=SPY&signal=golden_cross&eng=vectorized&entry=limit&exit=time&en.limit.offset_atr=1&ex.time.max_hold_bars=5",
    );
    // Without the defaults (a pinned run's link) the rules are always written.
    expect(writeBacktestForm({ ...form, entry: "next_open", entryParams: {}, exits: ["target", "time"] }).toString()).toContain(
      "entry=next_open&exit=target%2Ctime",
    );

    const none = readBacktestForm(new URLSearchParams("ticker=SPY&signal=golden_cross&exit=none"), config);
    expect(none.exits).toEqual([]);
    expect(writeBacktestForm(none, config).get("exit")).toBe("none");
    expect(backtestBody(none)?.exits).toEqual([]);
  });

  it("reads links from before trade rules, whose target and time exit were settings", () => {
    const url = "ticker=SPY&signal=golden_cross&set.backtest.target_r=3&set.backtest.commission_pct=0.2&set.backtest.max_hold_bars=10";
    const form = readBacktestForm(new URLSearchParams(url), config);
    expect(form.settings).toEqual({ backtest: { commission_pct: 0.2 } });
    expect(form.exitParams).toEqual({ target: { target_r: 3 }, time: { max_hold_bars: 10 } });
    // An exit the link switches off keeps none of its old parameters.
    expect(readBacktestForm(new URLSearchParams(`${url}&exit=time`), config).exitParams).toEqual({ time: { max_hold_bars: 10 } });
  });
});
