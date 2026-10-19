import type { ReactNode } from "react";

import type { RegimeOut } from "../api/client";
import { fmtNumber, fmtPrice } from "../lib/format";

const STYLES: Record<string, string> = {
  "risk-on": "bg-up/15 text-up",
  neutral: "bg-warn/15 text-warn",
  "risk-off": "bg-down/15 text-down",
};

function Position({ above, label }: { above: boolean | null; label: string }) {
  if (above === null) return <span className="text-muted">{label} n/a</span>;
  return <span className={above ? "text-up" : "text-down"}>{above ? `above ${label}` : `below ${label}`}</span>;
}

function Metric({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-muted">{label}</div>
      <div className="num text-sm font-medium">{children}</div>
    </div>
  );
}

export function RegimeBanner({ regime }: { regime: RegimeOut }) {
  return (
    <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-xl border border-line bg-panel px-4 py-3">
      <div>
        <div className="text-xs text-muted">Market regime</div>
        <span
          className={`mt-0.5 inline-flex rounded-md px-2 py-0.5 text-sm font-semibold uppercase ${STYLES[regime.regime] ?? ""}`}
        >
          {regime.regime}
        </span>
      </div>
      <Metric label={`Benchmark ${regime.benchmark}`}>
        {fmtPrice(regime.benchmark_close)} · <Position above={regime.benchmark_above_slow} label="SMA200" />
      </Metric>
      <Metric label="Breadth above SMA50 / SMA200">
        {fmtNumber(regime.pct_above_fast, 0)}% / {fmtNumber(regime.pct_above_slow, 0)}%{" "}
        <span className="text-muted">of {regime.universe_size}</span>
      </Metric>
      <Metric label="52-week highs / lows">
        <span className="text-up">{regime.new_highs}</span> / <span className="text-down">{regime.new_lows}</span>
      </Metric>
    </div>
  );
}
