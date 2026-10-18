import { useQuery } from "@tanstack/react-query";

import { api, type BacktestIn, type ChartIn, type EdgeIn, type PortfolioIn, type RotationIn, type ScanIn, type SweepIn, type WalkForwardIn, type WatchlistBacktestIn } from "./client";

const FIVE_MINUTES = 5 * 60_000;

export const useConfig = () => useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });

export const useSignals = () => useQuery({ queryKey: ["signals"], queryFn: api.signals, staleTime: Infinity });

export const useWatchlists = () => useQuery({ queryKey: ["watchlists"], queryFn: api.watchlists, staleTime: Infinity });

export const JOURNAL_KEY = ["journal"];

export const useJournal = () => useQuery({ queryKey: JOURNAL_KEY, queryFn: api.journal });

export const useScan = (body: ScanIn | null) =>
  useQuery({
    queryKey: ["scan", body],
    queryFn: () => api.scan(body as ScanIn),
    enabled: body !== null,
    staleTime: FIVE_MINUTES,
    retry: false,
  });

export const useEdge = (body: EdgeIn | null) =>
  useQuery({
    queryKey: ["edge", body],
    queryFn: () => api.edge(body as EdgeIn),
    enabled: body !== null,
    staleTime: FIVE_MINUTES,
    retry: false,
  });

export const useBacktest = (body: BacktestIn | null) =>
  useQuery({
    queryKey: ["backtest", body],
    queryFn: () => api.backtest(body as BacktestIn),
    enabled: body !== null,
    staleTime: FIVE_MINUTES,
    retry: false,
  });

export const useSweep = (body: SweepIn | null) =>
  useQuery({
    queryKey: ["sweep", body],
    queryFn: () => api.sweep(body as SweepIn),
    enabled: body !== null,
    staleTime: FIVE_MINUTES,
    retry: false,
  });

export const useWalkForward = (body: WalkForwardIn | null) =>
  useQuery({
    queryKey: ["walk-forward", body],
    queryFn: () => api.walkForward(body as WalkForwardIn),
    enabled: body !== null,
    staleTime: FIVE_MINUTES,
    retry: false,
  });

export const useWatchlistBacktest = (body: WatchlistBacktestIn | null) =>
  useQuery({
    queryKey: ["watchlist-backtest", body],
    queryFn: () => api.watchlistBacktest(body as WatchlistBacktestIn),
    enabled: body !== null,
    staleTime: FIVE_MINUTES,
    retry: false,
  });

export const usePortfolioBacktest = (body: PortfolioIn | null) =>
  useQuery({
    queryKey: ["portfolio-backtest", body],
    queryFn: () => api.portfolioBacktest(body as PortfolioIn),
    enabled: body !== null,
    staleTime: FIVE_MINUTES,
    retry: false,
  });

export const useRotationBacktest = (body: RotationIn | null) =>
  useQuery({
    queryKey: ["rotation-backtest", body],
    queryFn: () => api.rotationBacktest(body as RotationIn),
    enabled: body !== null,
    staleTime: FIVE_MINUTES,
    retry: false,
  });

export const useChart = (body: ChartIn | null) =>
  useQuery({
    queryKey: ["chart", body],
    queryFn: () => api.chart(body as ChartIn),
    enabled: body !== null,
    staleTime: FIVE_MINUTES,
    retry: false,
  });
