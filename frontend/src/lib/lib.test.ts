import { describe, expect, it } from "vitest";

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
    expect(backtestBody(readBacktestForm(new URLSearchParams("ticker=spy")))).toBeNull();
  });

  it("ignores unknown families and directions from the URL", () => {
    const form = readScanForm(new URLSearchParams("w=etf&dir=sideways&fam=trend,bogus"));
    expect(form.direction).toBe("both");
    expect(form.families).toEqual(["trend"]);
  });

  it("builds a backtest request with only the selected signal's parameters", () => {
    const url = "ticker=spy&signal=golden_cross&eng=vectorized,cerebro&set.risk.atr_mult=2.5&sig.golden_cross.fast=20&sig.death_cross.fast=5";
    const form = readBacktestForm(new URLSearchParams(url));
    expect(backtestBody(form)).toEqual({
      ticker: "SPY",
      signal: "golden_cross",
      engines: ["vectorized", "cerebro"],
      period: null,
      params: { fast: 20 },
      settings: { risk: { atr_mult: 2.5 } },
    });
    expect(writeBacktestForm(form).toString()).toBe(
      "ticker=SPY&signal=golden_cross&eng=vectorized%2Ccerebro&set.risk.atr_mult=2.5&sig.golden_cross.fast=20",
    );
  });
});
