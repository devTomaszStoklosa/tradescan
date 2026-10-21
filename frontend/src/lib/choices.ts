import type { WatchlistOut } from "../api/client";
import { tickerList, type Universe } from "./params";

/** Above this size a first run (download of every ticker) takes minutes rather than seconds. */
export const LARGE_UNIVERSE = 100;

export function universeSize(universe: Universe, watchlists: WatchlistOut[]): number {
  if (!universe.watchlist) return tickerList(universe.tickers).length;
  return watchlists.find((item) => item.name === universe.watchlist)?.tickers.length ?? 0;
}

/** Above this many tickers, the Cerebro reference takes minutes. */
const SLOW_CEREBRO_TICKERS = 20;

/** True when the Cerebro reference is picked for a universe big enough to make it slow. */
export const isSlowCerebro = (engines: readonly string[], universe: Universe, watchlists: WatchlistOut[]): boolean =>
  engines.includes("cerebro") && universeSize(universe, watchlists) > SLOW_CEREBRO_TICKERS;

/** `engines` with `engine` added when it is off and dropped when it is on. */
export const toggleEngine = (engines: readonly string[], engine: string): string[] =>
  engines.includes(engine) ? engines.filter((item) => item !== engine) : [...engines, engine];

/** CSS variables of the equity lines, one per engine run. */
export const ENGINE_COLORS = ["--accent", "--warn"];

/** History lengths offered in forms (yfinance periods). */
export const PERIODS = ["1y", "2y", "5y", "10y", "max"];

/** Settings a backtest uses, by section: the ATR stop from `risk` and everything in `backtest`. */
export const BACKTEST_FIELDS = { risk: ["atr_period", "atr_mult"] } as const;
export const BACKTEST_SECTIONS = ["risk", "backtest"] as const;
/** Settings of pyramiding, which only the single-ticker engines do: the max units and the distance between them. */
export const PYRAMID_SECTION = "pyramid";
/** Settings a single-ticker setup reads (Backtest, Sweep and Watchlist): the shared setup's and the pyramiding. */
export const SETUP_SECTIONS = [...BACKTEST_SECTIONS, PYRAMID_SECTION] as const;
/** Settings of the Monte Carlo of a run's trades, which only a single backtest runs. */
export const MONTE_CARLO_SECTION = "monte_carlo";
/** Settings the Backtest page reads: the single-ticker setup's and the Monte Carlo's. */
export const BACKTEST_PAGE_SECTIONS = [...SETUP_SECTIONS, MONTE_CARLO_SECTION] as const;
/** Settings of a portfolio backtest: the max positions and the max exposure. */
export const PORTFOLIO_SECTION = "portfolio";
/** Settings the Portfolio page reads: the shared setup's and the portfolio's. */
export const PORTFOLIO_PAGE_SECTIONS = [...BACKTEST_SECTIONS, PORTFOLIO_SECTION] as const;
/** Settings of a momentum rotation: the holdings and the absolute momentum check. */
export const ROTATION_SECTION = "rotation";
/** Settings the Rotation page reads: the rotation's, and the costs and out-of-sample share of `backtest`. */
export const ROTATION_PAGE_SECTIONS = [ROTATION_SECTION, "backtest"] as const;
/** Settings of a walk-forward: the windows, their in-sample length and the trades a pick needs. */
export const WALK_FORWARD_SECTION = "walk_forward";
/** Settings the Walk-forward page reads: the single-ticker setup's and the walk-forward's. */
export const WALK_FORWARD_PAGE_SECTIONS = [...SETUP_SECTIONS, WALK_FORWARD_SECTION] as const;
/** Settings of the scanner's score, which a priority rule that `needs_scan` reads too. */
export const SCORE_SECTIONS: readonly string[] = ["scoring", "trend", "scan"];
/** Of those sections, the parameters the score reads, where it reads only some. */
export const SCORE_FIELDS: Readonly<Record<string, readonly string[]>> = { scan: ["fresh_bars"] };

export function defaultWatchlist(watchlists: WatchlistOut[]): string {
  return watchlists.find((item) => item.name === "us_large")?.name ?? watchlists[0]?.name ?? "";
}

/** `form` with the default watchlist when it names no watchlist or tickers yet. */
export function withDefaultUniverse<F extends { universe: Universe }>(form: F, watchlists: WatchlistOut[]): F {
  if (form.universe.watchlist || form.universe.tickers) return form;
  return { ...form, universe: { watchlist: defaultWatchlist(watchlists), tickers: "" } };
}
