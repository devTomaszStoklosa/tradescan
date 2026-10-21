import { describe, expect, it } from "vitest";

import { config, rotationForm } from "../test/fixtures";
import {
  readRotationSweepForm,
  rotationSweepBody,
  rotationSweepParams,
  withRotationCombination,
  writeRotationSweepForm,
  type RotationSweepForm,
} from "./rotationSweep";

const URL =
  "w=etf&wt=inverse_volatility&set.rotation.holdings=3&ax1=settings.rotation.holdings&ax1v=2%3A4%3A1&ax2=ranking.lookback&ax2v=126%3A252%3A126";

const sweepForm = (changes: Partial<RotationSweepForm> = {}): RotationSweepForm => ({
  ...readRotationSweepForm(new URLSearchParams(URL), config),
  ...changes,
});

describe("rotation sweep form", () => {
  it("round-trips the rotation and its axes through the URL, without the engines", () => {
    const form = readRotationSweepForm(new URLSearchParams(`${URL}&eng=vectorized%2Ccerebro`), config);
    expect(form.engines).toEqual(["vectorized"]);
    expect(form.settings).toEqual({ rotation: { holdings: 3 } });
    expect(form.axes).toEqual([
      { key: "settings.rotation.holdings", from: 2, to: 4, step: 1 },
      { key: "ranking.lookback", from: 126, to: 252, step: 126 },
    ]);
    expect(writeRotationSweepForm(form, config).toString()).toBe(new URLSearchParams(URL).toString());
  });

  it("offers the ranking's, the weighting's, the rotation's and the costs' single numbers, not the split", () => {
    const params = rotationSweepParams(sweepForm(), config);
    expect(params.map((param) => [param.key, param.group, param.current])).toEqual([
      ["ranking.lookback", "Ranking: Momentum", 252],
      ["ranking.skip", "Ranking: Momentum", 21],
      ["weighting.lookback", "Weights: Inverse volatility", 63],
      ["settings.rotation.holdings", "Rotation", 3],
      ["settings.rotation.absolute_lookback", "Rotation", 252],
      ["settings.backtest.commission_pct", "Backtest", 0.1],
      ["settings.backtest.slippage_pct", "Backtest", 0.05],
    ]);
    // Relative strength's lookbacks are a list and equal weights have no parameter.
    const plain = rotationSweepParams(sweepForm({ ranking: "relative_strength", weighting: "equal" }), config);
    expect(plain.filter((param) => param.target !== "settings")).toEqual([]);
  });

  it("builds the request without the engines, and none while an axis or the setup is invalid", () => {
    const form = sweepForm();
    const params = rotationSweepParams(form, config);
    const body = rotationSweepBody(form, params, config.rotation_sweep);
    expect(body).not.toHaveProperty("engines");
    expect(body).toMatchObject({
      watchlist: "etf",
      weighting: { name: "inverse_volatility", params: {} },
      settings: { rotation: { holdings: 3 } },
      axes: [
        { target: "settings", owner: "rotation", name: "holdings", values: [2, 3, 4] },
        { target: "ranking", owner: null, name: "lookback", values: [126, 252] },
      ],
    });
    const limits = config.rotation_sweep;
    expect(rotationSweepBody({ ...form, axes: [] }, params, limits)).toBeNull();
    expect(
      rotationSweepBody({ ...form, axes: [{ key: "ranking.lookback", from: 1, to: 9, step: 1 }] }, params, limits),
    ).toBeNull();
    expect(rotationSweepBody({ ...form, universe: { watchlist: "", tickers: "" } }, params, limits)).toBeNull();
    const many = [
      { key: "ranking.lookback", from: 2, to: 50, step: 1 },
      { key: "ranking.skip", from: 0, to: 10, step: 1 },
    ];
    expect(rotationSweepBody({ ...form, axes: many }, params, limits)).toBeNull(); // 49 × 11 combinations
  });

  it("sets a combination's values on the rotation, leaving out the defaults", () => {
    const params = rotationSweepParams(rotationForm, config).filter((param) =>
      ["settings.rotation.holdings", "ranking.lookback", "weighting.lookback"].includes(param.key),
    );
    expect(withRotationCombination(rotationForm, params, [126, 20, 4])).toEqual({
      ...rotationForm,
      rankingParams: { lookback: 126 },
      weightingParams: { lookback: 20 },
      settings: { rotation: { holdings: 4 } },
    });
    expect(withRotationCombination(rotationForm, params, [252, 63, 5])).toEqual({ ...rotationForm, settings: {} });
  });
});
