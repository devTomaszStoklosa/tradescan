import type { CSSProperties } from "react";

import type { Family } from "../api/client";

export const FAMILY_LABELS: Record<Family, string> = {
  trend: "Trend",
  momentum: "Momentum",
  breakout: "Breakout",
  mean_reversion: "Mean reversion",
  volume: "Volume",
  pattern: "Pattern",
};

export const familyColor = (family: Family) => `var(--fam-${family})`;

export function SignalChip({ name, family, barsAgo }: { name: string; family: Family; barsAgo?: number }) {
  return (
    <span
      className="chip inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium"
      style={{ "--chip": familyColor(family) } as CSSProperties}
      title={`${FAMILY_LABELS[family]}${barsAgo !== undefined ? `, fired ${barsAgo === 0 ? "on the last bar" : `${barsAgo} bar(s) ago`}` : ""}`}
    >
      {name}
      {barsAgo !== undefined && <span className="num opacity-70">{barsAgo}</span>}
    </span>
  );
}
