import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Candle, Point } from "../../api/client";
import { withAlpha } from "../../lib/cssVar";
import { useTheme } from "../../state/theme";
import { baseOptions, chartPalette, toneColor, type Tone } from "./theme";

export interface ChartMarker {
  time: string;
  position: "aboveBar" | "belowBar" | "inBar";
  shape: "arrowUp" | "arrowDown" | "circle" | "square";
  tone: Tone;
  text?: string;
}

export interface PriceLevel {
  price: number;
  label: string;
  tone: Tone;
}

interface PriceChartProps {
  candles: Candle[];
  smaFast?: Point[];
  smaSlow?: Point[];
  markers?: ChartMarker[];
  levels?: PriceLevel[];
  /** Bars visible initially (the user can scroll back); all bars when omitted. */
  visibleBars?: number;
  height?: number;
  label: string;
}

export function PriceChart({ candles, smaFast, smaSlow, markers, levels, visibleBars, height = 380, label }: PriceChartProps) {
  const container = useRef<HTMLDivElement>(null);
  const { resolved } = useTheme();

  useEffect(() => {
    const element = container.current;
    if (!element || !candles.length) return;
    const palette = chartPalette();
    const chart = createChart(element, baseOptions(palette));

    const price = chart.addSeries(CandlestickSeries, {
      upColor: palette.up,
      downColor: palette.down,
      wickUpColor: palette.up,
      wickDownColor: palette.down,
      borderVisible: false,
    });
    price.setData(candles.map(({ time, open, high, low, close }) => ({ time: time as Time, open, high, low, close })));

    const volume = chart.addSeries(HistogramSeries, { priceScaleId: "volume", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(
      candles.map((candle) => ({
        time: candle.time as Time,
        value: candle.volume,
        color: withAlpha(candle.close >= candle.open ? palette.up : palette.down, 0.35),
      })),
    );

    for (const [points, color] of [
      [smaFast, palette.fast],
      [smaSlow, palette.slow],
    ] as const) {
      if (!points?.length) continue;
      const line = chart.addSeries(LineSeries, { color, lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
      line.setData(points.map((point) => ({ time: point.time as Time, value: point.value })));
    }

    if (markers?.length) {
      const sorted: SeriesMarker<Time>[] = [...markers]
        .sort((a, b) => a.time.localeCompare(b.time))
        .map((marker) => ({
          time: marker.time as Time,
          position: marker.position,
          shape: marker.shape,
          color: toneColor(palette, marker.tone),
          text: marker.text,
        }));
      createSeriesMarkers(price, sorted);
    }

    for (const level of levels ?? []) {
      price.createPriceLine({
        price: level.price,
        color: toneColor(palette, level.tone),
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
        axisLabelVisible: true,
        title: level.label,
      });
    }

    // autoSize measures the container asynchronously; set the range once the real width is known.
    const frame = requestAnimationFrame(() => {
      if (visibleBars && candles.length > visibleBars) {
        chart.timeScale().setVisibleLogicalRange({ from: candles.length - visibleBars, to: candles.length + 2 });
      } else {
        chart.timeScale().fitContent();
      }
    });
    return () => {
      cancelAnimationFrame(frame);
      chart.remove();
    };
  }, [candles, smaFast, smaSlow, markers, levels, visibleBars, resolved]);

  return (
    <div>
      <div className="mb-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <LegendItem color="var(--chart-sma-fast)" label="SMA 50" />
        <LegendItem color="var(--chart-sma-slow)" label="SMA 200" />
        {markers?.length ? <span>▲▼ markers: signal events / trades</span> : null}
      </div>
      <div ref={container} role="img" aria-label={label} style={{ height }} className="w-full overflow-hidden rounded-lg" />
    </div>
  );
}

export function LegendItem({ color, label, dashed = false }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden
        className="inline-block w-4 border-t-2"
        style={{ borderColor: color, borderTopStyle: dashed ? "dashed" : "solid" }}
      />
      {label}
    </span>
  );
}
