type Maybe = number | null | undefined;

export const DASH = "–";

const isMissing = (value: Maybe): value is null | undefined =>
  value === null || value === undefined || Number.isNaN(value);

export function fmtNumber(value: Maybe, digits = 2): string {
  if (isMissing(value)) return DASH;
  // Tiny negative values that round to zero would otherwise print as "-0.00".
  const safe = Number(value.toFixed(digits)) === 0 ? 0 : value;
  return safe.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Prices: more decimals for cheap instruments (crypto, penny stocks). */
export function fmtPrice(value: Maybe): string {
  if (isMissing(value)) return DASH;
  const magnitude = Math.abs(value);
  return fmtNumber(value, magnitude >= 1 ? 2 : magnitude >= 0.01 ? 4 : 6);
}

/** Values that are already percentages (e.g. 12.3 means 12.3%). */
export function fmtPct(value: Maybe, digits = 1, signed = false): string {
  if (isMissing(value)) return DASH;
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${fmtNumber(value, digits)}%`;
}

export function fmtSigned(value: Maybe, digits = 2): string {
  if (isMissing(value)) return DASH;
  return `${value > 0 ? "+" : ""}${fmtNumber(value, digits)}`;
}

export function fmtCompact(value: Maybe): string {
  if (isMissing(value)) return DASH;
  return value.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 });
}

/** Sizes: whole units for stocks, fractional for crypto lots. */
export function fmtSize(value: Maybe): string {
  if (isMissing(value)) return DASH;
  return Number.isInteger(value) ? value.toLocaleString("en-US") : fmtNumber(value, 4);
}

/** A parameter's value as settings hold it: a number, a list of numbers or numbers by key. */
export function fmtParam(value: number | number[] | Record<string, number>): string {
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.join(", ");
  return Object.entries(value)
    .map(([key, item]) => `${key}: ${item}`)
    .join(", ");
}

/** Tailwind text class for a signed value. */
export function tone(value: Maybe): string {
  if (isMissing(value) || value === 0) return "";
  return value > 0 ? "text-up" : "text-down";
}
