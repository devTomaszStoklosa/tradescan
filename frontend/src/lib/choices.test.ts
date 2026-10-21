import { describe, expect, it } from "vitest";

import type { WatchlistOut } from "../api/client";
import { isSlowCerebro, toggleEngine } from "./choices";
import { commaList } from "./params";

const tickers = (count: number) => Array.from({ length: count }, (_, index) => `T${index}`).join(",");
const watchlists = [{ name: "big", tickers: Array.from({ length: 30 }, (_, i) => `W${i}`) }] as WatchlistOut[];

describe("toggleEngine", () => {
  it("adds an engine that is off and drops one that is on", () => {
    expect(toggleEngine(["vectorized"], "cerebro")).toEqual(["vectorized", "cerebro"]);
    expect(toggleEngine(["vectorized", "cerebro"], "vectorized")).toEqual(["cerebro"]);
  });
});

describe("isSlowCerebro", () => {
  it("needs cerebro and more than 20 tickers", () => {
    expect(isSlowCerebro(["cerebro"], { watchlist: "", tickers: tickers(21) }, [])).toBe(true);
    expect(isSlowCerebro(["cerebro"], { watchlist: "", tickers: tickers(20) }, [])).toBe(false);
    expect(isSlowCerebro(["vectorized"], { watchlist: "", tickers: tickers(21) }, [])).toBe(false);
    expect(isSlowCerebro(["cerebro"], { watchlist: "big", tickers: "" }, watchlists)).toBe(true);
  });
});

describe("commaList", () => {
  it("trims items and drops empty ones", () => {
    expect(commaList(" vectorized, ,cerebro ")).toEqual(["vectorized", "cerebro"]);
    expect(commaList(null)).toEqual([]);
  });
});
