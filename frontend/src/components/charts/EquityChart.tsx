import { LineSeries, LineStyle, createChart, type PriceFormat, type Time } from "lightweight-charts";
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
}: {
  series: EquitySeries[];
  height?: number;
  format?: EquityFormat;
  label?: string;
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
    }
    // autoSize measures the container asynchronously; fit once the real width is known.
    const frame = requestAnimationFrame(() => chart.timeScale().fitContent());
    return () => {
      cancelAnimationFrame(frame);
      chart.remove();
    };
  }, [series, resolved, format]);

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
