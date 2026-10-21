import { skipToken, useQuery } from "@tanstack/react-query";

import {
  api,
  type BacktestIn,
  type ChartIn,
  type EdgeIn,
  type PortfolioIn,
  type RotationIn,
  type RotationSweepIn,
  type ScanIn,
  type SweepIn,
  type WalkForwardIn,
  type WatchlistBacktestIn,
} from "./client";

const FIVE_MINUTES = 5 * 60_000;

export const useConfig = () => useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });

export const useSignals = () => useQuery({ queryKey: ["signals"], queryFn: api.signals, staleTime: Infinity });

export const useWatchlists = () => useQuery({ queryKey: ["watchlists"], queryFn: api.watchlists, staleTime: Infinity });

export const JOURNAL_KEY = ["journal"];

export const useJournal = () => useQuery({ queryKey: JOURNAL_KEY, queryFn: api.journal });

/** Runs `fetch` with `body`, and waits while there is no body: a form not submitted yet or not valid. */
function useRun<In, Out>(key: string, fetch: (body: In) => Promise<Out>, body: In | null) {
  return useQuery({
    queryKey: [key, body],
    queryFn: body === null ? skipToken : () => fetch(body),
    staleTime: FIVE_MINUTES,
    retry: false,
  });
}

export const useScan = (body: ScanIn | null) => useRun("scan", api.scan, body);
export const useEdge = (body: EdgeIn | null) => useRun("edge", api.edge, body);
export const useBacktest = (body: BacktestIn | null) => useRun("backtest", api.backtest, body);
export const useSweep = (body: SweepIn | null) => useRun("sweep", api.sweep, body);
export const useWalkForward = (body: WalkForwardIn | null) => useRun("walk-forward", api.walkForward, body);
export const useWatchlistBacktest = (body: WatchlistBacktestIn | null) =>
  useRun("watchlist-backtest", api.watchlistBacktest, body);
export const usePortfolioBacktest = (body: PortfolioIn | null) =>
  useRun("portfolio-backtest", api.portfolioBacktest, body);
export const useRotationBacktest = (body: RotationIn | null) => useRun("rotation-backtest", api.rotationBacktest, body);
export const useRotationSweep = (body: RotationSweepIn | null) => useRun("rotation-sweep", api.rotationSweep, body);
export const useChart = (body: ChartIn | null) => useRun("chart", api.chart, body);
