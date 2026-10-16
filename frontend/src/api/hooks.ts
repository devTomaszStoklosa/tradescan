import { useQuery } from "@tanstack/react-query";

import { api, type BacktestIn, type ChartIn, type EdgeIn, type ScanIn, type SweepIn, type WatchlistBacktestIn } from "./client";

const FIVE_MINUTES = 5 * 60_000;

export const useConfig = () => useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });

export const useSignals = () => useQuery({ queryKey: ["signals"], queryFn: api.signals, staleTime: Infinity });

export const useWatchlists = () => useQuery({ queryKey: ["watchlists"], queryFn: api.watchlists, staleTime: Infinity });

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

export const useWatchlistBacktest = (body: WatchlistBacktestIn | null) =>
  useQuery({
    queryKey: ["watchlist-backtest", body],
    queryFn: () => api.watchlistBacktest(body as WatchlistBacktestIn),
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
