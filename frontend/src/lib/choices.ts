import type { WatchlistOut } from "../api/client";

/** History lengths offered in forms (yfinance periods). */
export const PERIODS = ["1y", "2y", "5y", "10y", "max"];

export function defaultWatchlist(watchlists: WatchlistOut[]): string {
  return watchlists.find((item) => item.name === "us_large")?.name ?? watchlists[0]?.name ?? "";
}
