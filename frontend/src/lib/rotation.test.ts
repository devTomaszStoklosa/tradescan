import { describe, expect, it } from "vitest";

import { config } from "../test/fixtures";
import { hasRotationProblems, readRotationForm, resetRotation, rotationBody, rotationChanges, writeRotationForm } from "./rotation";

const URL =
  "w=etf&p=5y&rank=relative_strength&wt=inverse_volatility&reb=weekly&safe=TLT&b=QQQ&set.rotation.holdings=3&set.backtest.commission_pct=0.05&wp.inverse_volatility.lookback=20";

describe("rotation form", () => {
  it("round-trips the universe, the rules, the rebalance, the safe asset and the settings through the URL", () => {
    const form = readRotationForm(new URLSearchParams(URL), config);
    expect(form).toEqual({
      universe: { watchlist: "etf", tickers: "" },
      period: "5y",
      ranking: "relative_strength",
      rankingParams: {},
      weighting: "inverse_volatility",
      weightingParams: { lookback: 20 },
      rebalance: "weekly",
      safeAsset: "TLT",
      benchmark: "QQQ",
      settings: { rotation: { holdings: 3 }, backtest: { commission_pct: 0.05 } },
    });
    expect(writeRotationForm(form, config).toString()).toBe(new URLSearchParams(URL).toString());
  });

  it("leaves the defaults out of the URL and reads them back", () => {
    const form = readRotationForm(new URLSearchParams("t=xle,xlk&reb=daily&set.risk.atr_mult=3&rk.momentum.skip=0"), config);
    expect(form).toMatchObject({ ranking: "momentum", rankingParams: { skip: 0 }, weighting: "equal", rebalance: "monthly", safeAsset: "", settings: {} });
    expect(writeRotationForm(form, config).toString()).toBe("t=XLE%2CXLK&rk.momentum.skip=0");
  });

  it("builds the request with both rules, the rebalance and the safe asset", () => {
    const form = readRotationForm(new URLSearchParams(URL), config);
    expect(rotationBody(form)).toEqual({
      watchlist: "etf",
      period: "5y",
      ranking: { name: "relative_strength", params: {} },
      weighting: { name: "inverse_volatility", params: { lookback: 20 } },
      rebalance: "weekly",
      safe_asset: "TLT",
      benchmark: "QQQ",
      settings: { rotation: { holdings: 3 }, backtest: { commission_pct: 0.05 } },
    });
    expect(rotationBody({ ...form, safeAsset: " ", benchmark: "" })).toMatchObject({ safe_asset: null, benchmark: null });
    expect(rotationBody({ ...form, universe: { watchlist: "", tickers: " " } })).toBeNull();
  });

  it("counts, checks and resets everything but the universe", () => {
    const form = readRotationForm(new URLSearchParams(URL), config);
    expect(rotationChanges(form, config)).toBe(9); // the history, both rules, a weighting parameter, the rebalance, safe asset, benchmark and 2 settings
    expect(hasRotationProblems(form, config)).toBe(false);
    expect(hasRotationProblems({ ...form, ranking: "score" }, config)).toBe(true); // reads the scanner, so no ranking
    expect(hasRotationProblems({ ...form, weightingParams: { lookback: 1 } }, config)).toBe(true);
    expect(hasRotationProblems({ ...form, settings: { rotation: { holdings: 0 } } }, config)).toBe(true);
    expect(hasRotationProblems({ ...form, settings: { risk: { atr_mult: 3 } } }, config)).toBe(true); // not a section it offers
    expect(hasRotationProblems({ ...form, safeAsset: "TLT IEF" }, config)).toBe(true);
    const reset = resetRotation(form, config);
    expect(reset.universe).toEqual(form.universe);
    expect(rotationChanges(reset, config)).toBe(0);
  });
});
