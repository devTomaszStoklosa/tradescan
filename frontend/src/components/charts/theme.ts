import { ColorType, CrosshairMode, type DeepPartial, type ChartOptions } from "lightweight-charts";

import { cssVar } from "../../lib/cssVar";

export type Tone = "up" | "down" | "accent" | "muted" | "fast" | "slow";

/** Chart colours read from the CSS theme tokens, so canvases match the rest of the page. */
export function chartPalette() {
  return {
    panel: cssVar("--panel"),
    fg: cssVar("--fg"),
    muted: cssVar("--muted"),
    line: cssVar("--line"),
    grid: cssVar("--chart-grid"),
    up: cssVar("--up"),
    down: cssVar("--down"),
    accent: cssVar("--accent"),
    warn: cssVar("--warn"),
    fast: cssVar("--chart-sma-fast"),
    slow: cssVar("--chart-sma-slow"),
    benchmark: cssVar("--chart-benchmark"),
  };
}

export type Palette = ReturnType<typeof chartPalette>;

export function toneColor(palette: Palette, tone: Tone): string {
  return { up: palette.up, down: palette.down, accent: palette.accent, muted: palette.muted, fast: palette.fast, slow: palette.slow }[tone];
}

export function baseOptions(palette: Palette): DeepPartial<ChartOptions> {
  return {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: palette.panel },
      textColor: palette.muted,
      fontFamily: getComputedStyle(document.body).fontFamily,
      attributionLogo: true,
    },
    grid: { vertLines: { color: palette.grid }, horzLines: { color: palette.grid } },
    rightPriceScale: { borderColor: palette.line },
    timeScale: { borderColor: palette.line },
    crosshair: { mode: CrosshairMode.Normal },
    // Charts sit inside a scrolling page: the mouse wheel scrolls the page; drag pans, axis drag zooms.
    handleScroll: { mouseWheel: false },
    handleScale: { mouseWheel: false },
  };
}
