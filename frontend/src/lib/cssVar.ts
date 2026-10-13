/** Resolved value of a CSS custom property on <html>; lets canvas charts follow the CSS theme. */
export function cssVar(name: string, fallback = "#888888"): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** Same colour with alpha, for hex colours (#rrggbb). */
export function withAlpha(hex: string, alpha: number): string {
  const match = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!match?.[1]) return hex;
  const channel = Math.round(Math.min(Math.max(alpha, 0), 1) * 255)
    .toString(16)
    .padStart(2, "0");
  return `#${match[1]}${channel}`;
}
