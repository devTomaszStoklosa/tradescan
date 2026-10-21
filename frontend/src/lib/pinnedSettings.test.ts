import { describe, expect, it } from "vitest";

import { backtestForm, backtestResult, makePortfolioPin, makeRotationPin } from "../test/fixtures";
import { pinnedSettings, reopenedSettings } from "./pinnedSettings";
import { snapshotRun, toPinnedRun } from "./runs";

const backtestPin = () => toPinnedRun(snapshotRun(backtestResult, "vectorized", backtestForm)!);

describe("pinned settings", () => {
  it("restores the stop, costs and pyramiding a backtest used", () => {
    const pin = backtestPin();
    const settings = pinnedSettings(pin);
    expect(settings.risk).toEqual({ atr_period: pin.config.atr_period, atr_mult: pin.config.atr_mult });
    expect(settings.pyramid).toEqual({ max_units: pin.config.max_units, add_every_atr: pin.config.add_every_atr });
    expect(settings.backtest?.commission_pct).toBe(pin.config.commission_pct);
    expect(settings.account).toBeUndefined();
  });

  it("keeps a value equal to today's default, which the form dropped", () => {
    const pin = {
      ...backtestPin(),
      config: { ...backtestPin().config, max_units: 1 },
      form: { ...backtestForm, settings: {} },
    };
    expect(reopenedSettings(pin).pyramid?.max_units).toBe(1);
  });

  it("lets the recorded value win over the form's", () => {
    const pin = backtestPin();
    const form = { ...pin.form, settings: { risk: { atr_mult: 99 }, scan: { fresh_bars: 5 } } };
    const settings = reopenedSettings({ ...pin, form });
    expect(settings.risk?.atr_mult).toBe(pin.config.atr_mult);
    expect(settings.scan).toEqual({ fresh_bars: 5 });
  });

  it("skips what an older pin did not record", () => {
    const pin = backtestPin();
    const { oos_pct: _oos, ...config } = pin.config;
    expect(pinnedSettings({ ...pin, config }).backtest).not.toHaveProperty("oos_pct");
  });

  it("restores a portfolio's limits without pyramiding", () => {
    const pin = makePortfolioPin(1);
    const settings = pinnedSettings(pin);
    expect(settings.portfolio).toEqual({
      max_positions: pin.portfolio.max_positions,
      max_exposure_pct: pin.portfolio.max_exposure_pct,
    });
    expect(settings.pyramid).toBeUndefined();
  });

  it("restores a rotation's holdings, lookback and costs", () => {
    const pin = makeRotationPin(1);
    const settings = pinnedSettings(pin);
    expect(settings.rotation).toEqual({
      holdings: pin.rotation.holdings,
      absolute_lookback: pin.rotation.absolute_lookback,
    });
    expect(settings.backtest?.commission_pct).toBe(pin.config.commission_pct);
  });
});
