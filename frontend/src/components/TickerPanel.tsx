import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router";

import type { ChartIn, EdgeIn, HitOut } from "../api/client";
import { useChart, useConfig, useEdge } from "../api/hooks";
import { fmtNumber, fmtPct, fmtPrice, fmtSigned, fmtSize, tone } from "../lib/format";
import { BACKTEST_FIELDS } from "../lib/choices";
import { pickFields, pickOwners, type Overrides } from "../lib/overrides";
import { writeBacktestForm } from "../lib/params";
import { defaultRules } from "../lib/rules";
import { PriceChart, type ChartMarker, type PriceLevel } from "./charts/PriceChart";
import { EdgeTable } from "./EdgeTable";
import { SignalChip } from "./SignalChip";
import { Button, DirectionBadge, ErrorBox, Loading, StatTile } from "./ui";

const HORIZONS = [5, 10, 20];

export function TickerPanel({
  hit,
  settings,
  signalParams,
  period,
  onClose,
}: {
  hit: HitOut;
  /** The scan's overrides, so the chart, edge and backtest links use the same parameters. */
  settings: Overrides;
  signalParams: Overrides;
  period: string;
  onClose: () => void;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const signals = useMemo(() => hit.fired.map((item) => item.name), [hit]);
  const params = useMemo(() => pickOwners(signalParams, signals) as ChartIn["signal_params"], [signalParams, signals]);
  const chartBody = useMemo<ChartIn>(
    () => ({ ticker: hit.ticker, signals, signal_params: params, period: period || null }),
    [hit, signals, params, period],
  );
  const chart = useChart(chartBody);
  const edgeBody = useMemo<EdgeIn>(
    () => ({ tickers: [hit.ticker], signals, signal_params: params, horizons: HORIZONS, min_events: 0 }),
    [hit, signals, params],
  );
  const edge = useEdge(edgeBody);
  const defaults = useConfig().data; // loaded by the scan page already; backtest links use its default trade rules

  useEffect(() => {
    closeButton.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const markers = useMemo<ChartMarker[]>(
    () =>
      (chart.data?.events ?? []).map((event) => ({
        time: event.time,
        position: event.direction === "long" ? "belowBar" : "aboveBar",
        shape: event.direction === "long" ? "arrowUp" : "arrowDown",
        tone: event.direction === "long" ? "up" : "down",
      })),
    [chart.data],
  );

  const levels = useMemo<PriceLevel[]>(() => {
    const result: PriceLevel[] = [{ price: hit.risk.entry, label: "entry", tone: "accent" }];
    if (hit.risk.stop !== null) result.push({ price: hit.risk.stop, label: "stop", tone: "down" });
    hit.risk.targets.forEach((target, index) => {
      if (target !== null) result.push({ price: target, label: `T${index + 1}`, tone: "up" });
    });
    return result;
  }, [hit]);

  const { score, risk } = hit;
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label={`${hit.ticker} details`}>
      <button type="button" aria-label="Close details" className="absolute inset-0 bg-black/40" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-4xl flex-col gap-4 overflow-y-auto bg-bg p-4 shadow-2xl sm:p-6">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-mono text-2xl font-semibold">{hit.ticker}</h2>
              <DirectionBadge direction={hit.direction} />
            </div>
            <p className="num text-sm text-muted">
              {fmtPrice(hit.close)} <span className={tone(hit.change_pct)}>{fmtPct(hit.change_pct, 2, true)}</span> · as of {hit.date} ·
              ADX {fmtNumber(hit.adx, 0)}
            </p>
          </div>
          <Button ref={closeButton} onClick={onClose}>
            Close
          </Button>
        </header>

        <section className="rounded-xl border border-line bg-panel p-3">
          {chart.isLoading && <Loading message="Loading chart…" />}
          {chart.isError && <ErrorBox error={chart.error} onRetry={() => chart.refetch()} />}
          {chart.data && (
            <PriceChart
              label={`${hit.ticker} price chart with signal events and trade levels`}
              candles={chart.data.candles}
              smaFast={chart.data.sma_fast}
              smaSlow={chart.data.sma_slow}
              markers={markers}
              levels={levels}
              visibleBars={180}
            />
          )}
        </section>

        <section>
          <h3 className="mb-2 text-sm font-semibold">Risk plan</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatTile label="Entry (last close)" value={fmtPrice(risk.entry)} />
            <StatTile label="Stop" value={fmtPrice(risk.stop)} valueClass="text-down" sub={`risk ${fmtPrice(risk.risk_per_share)} / unit`} />
            <StatTile
              label="Targets"
              value={risk.targets.map((target) => fmtPrice(target)).join(" / ")}
              valueClass="text-up"
            />
            <StatTile
              label="Size"
              value={fmtSize(risk.size)}
              sub={`${fmtNumber(risk.position_value, 0)} value · ${fmtNumber(risk.risk_amount, 0)} at risk`}
            />
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-sm font-semibold">
            Score {fmtNumber(score.total, 1)}
          </h3>
          <dl className="num grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            {[
              ["Signals", score.signals],
              ["Daily trend", score.trend],
              ["Weekly trend", score.weekly],
              ["Relative strength", score.relative_strength],
            ].map(([label, value]) => (
              <div key={label as string} className="rounded-lg border border-line bg-panel px-3 py-2">
                <dt className="text-xs text-muted">{label}</dt>
                <dd className={`font-medium ${tone(value as number)}`}>{fmtSigned(value as number, 1)}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section>
          <h3 className="mb-2 text-sm font-semibold">Fired signals: history on {hit.ticker}</h3>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
            {defaults &&
              hit.fired.map((item) => (
                <Link
                  key={item.name}
                  className="inline-flex items-center gap-1 rounded-md hover:opacity-80"
                  to={`/backtest?${writeBacktestForm(
                    {
                      ticker: hit.ticker,
                      signal: item.name,
                      engines: ["vectorized"],
                      period: "",
                      settings: pickFields(settings, BACKTEST_FIELDS), // the scan's ATR stop rule
                      signalParams: signalParams[item.name] ?? {},
                      ...defaultRules(defaults),
                    },
                    defaults,
                  )}`}
                  title={`Backtest ${item.name} on ${hit.ticker}`}
                >
                  <SignalChip name={item.name} family={item.family} />
                  <span className="text-xs text-accent">backtest →</span>
                </Link>
              ))}
          </div>
          {edge.isLoading && <Loading message="Computing historical edge…" />}
          {edge.isError && <ErrorBox error={edge.error} onRetry={() => edge.refetch()} />}
          {edge.data && <EdgeTable rows={edge.data.rows} horizons={edge.data.horizons} />}
        </section>
      </aside>
    </div>
  );
}
