import type { WatchlistOut } from "../api/client";
import { tickerList, type Universe } from "./params";

/** Above this size a first run (download of every ticker) takes minutes rather than seconds. */
export const LARGE_UNIVERSE = 100;

export function universeSize(universe: Universe, watchlists: WatchlistOut[]): number {
  if (!universe.watchlist) return tickerList(universe.tickers).length;
  return watchlists.find((item) => item.name === universe.watchlist)?.tickers.length ?? 0;
}

/** History lengths offered in forms (yfinance periods). */
export const PERIODS = ["1y", "2y", "5y", "10y", "max"];

/** Settings a backtest uses, by section: the ATR stop from `risk` and everything in `backtest`. */
export const BACKTEST_FIELDS = { risk: ["atr_period", "atr_mult"] } as const;
export const BACKTEST_SECTIONS = ["risk", "backtest"] as const;
/** Settings of the Monte Carlo of a run's trades, which only a single backtest runs. */
export const MONTE_CARLO_SECTION = "monte_carlo";
/** Settings the Backtest page reads: the shared setup's and the Monte Carlo's. */
export const BACKTEST_PAGE_SECTIONS = [...BACKTEST_SECTIONS, MONTE_CARLO_SECTION] as const;

export function defaultWatchlist(watchlists: WatchlistOut[]): string {
  return watchlists.find((item) => item.name === "us_large")?.name ?? watchlists[0]?.name ?? "";
}
