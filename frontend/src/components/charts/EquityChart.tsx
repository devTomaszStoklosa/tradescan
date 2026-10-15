import { LineSeries, LineStyle, createChart, createSeriesMarkers, type ISeriesApi, type PriceFormat, type Time } from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Point } from "../../api/client";
import { fmtNumber } from "../../lib/format";
import { useTheme } from "../../state/theme";
import { LegendItem } from "./PriceChart";
import { baseOptions, chartPalette } from "./theme";

export interface EquitySeries {
  label: string;
  points: Point[];
  /** CSS colour token name, e.g. "--accent". */
  colorVar: string;
  dashed?: boolean;
  /** "left" gives the series its own axis, so a much larger benchmark does not flatten the strategy curve. */
  axis?: "left" | "right";
}

/** A labelled point in time, e.g. where the out-of-sample period starts. Drawn on the first series. */
export interface EquityEvent {
  time: string;
  text: string;
}

// A stable default, so a chart without events is not rebuilt on every render.
const NO_EVENTS: EquityEvent[] = [];

/** "price" shows whole currency units; "percent" shows returns with one decimal and a % sign. */
export type EquityFormat = "price" | "percent";

// A custom formatter for percent: the built-in "percent" type reads `precision` as a price scale and drops the decimals.
const PRICE_FORMATS: Record<EquityFormat, PriceFormat> = {
  price: { type: "price", precision: 0, minMove: 1 },
  percent: { type: "custom", minMove: 0.1, formatter: (value: number) => `${fmtNumber(value, 1)}%` },
};

export function EquityChart({
  series,
  height = 300,
  format = "price",
  label = "Equity curve",
  events = NO_EVENTS,
}: {
  series: EquitySeries[];
  height?: number;
  format?: EquityFormat;
  label?: string;
  events?: EquityEvent[];
}) {
  const container = useRef<HTMLDivElement>(null);
  const { resolved } = useTheme();

  useEffect(() => {
    const element = container.current;
    if (!element || !series.length) return;
    const palette = chartPalette();
    const usesLeftAxis = series.some((item) => item.axis === "left");
    const base = baseOptions(palette);
    const chart = createChart(element, {
      ...base,
      leftPriceScale: { visible: usesLeftAxis, borderColor: palette.line },
      // Ten years of daily bars must fit the width, so allow sub-pixel bar spacing.
      timeScale: { ...base.timeScale, minBarSpacing: 0.01 },
    });
    const styles = getComputedStyle(document.documentElement);
    const lines: ISeriesApi<"Line">[] = [];
    for (const item of series) {
      const line = chart.addSeries(LineSeries, {
        color: styles.getPropertyValue(item.colorVar).trim() || palette.accent,
        lineWidth: 2,
        lineStyle: item.dashed ? LineStyle.Dashed : LineStyle.Solid,
        title: item.label,
        priceLineVisible: false,
        priceScaleId: item.axis ?? "right",
        priceFormat: PRICE_FORMATS[format],
      });
      line.setData(item.points.map((point) => ({ time: point.time as Time, value: point.value })));
      lines.push(line);
    }
    const [first] = lines;
    if (first && events.length) {
      createSeriesMarkers(
        first,
        events.map((event) => ({ time: event.time as Time, position: "aboveBar" as const, shape: "arrowDown" as const, color: palette.muted, text: event.text })),
      );
    }
    // autoSize measures the container asynchronously; fit once the real width is known.
    const frame = requestAnimationFrame(() => chart.timeScale().fitContent());
    return () => {
      cancelAnimationFrame(frame);
      chart.remove();
    };
  }, [series, resolved, format, events]);

  return (
    <div>
      <div className="mb-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {series.map((item) => (
          <LegendItem
            key={item.label}
            color={`var(${item.colorVar})`}
            label={item.axis === "left" ? `${item.label} (left axis)` : item.label}
            dashed={item.dashed}
          />
        ))}
      </div>
      <div ref={container} role="img" aria-label={label} style={{ height }} className="w-full overflow-hidden rounded-lg" />
    </div>
  );
}
