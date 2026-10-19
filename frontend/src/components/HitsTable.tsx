import type { HitOut } from "../api/client";
import { fmtNumber, fmtPct, fmtPrice, fmtSigned, fmtSize, tone } from "../lib/format";
import { DataTable, type Column } from "./DataTable";
import { SignalChip } from "./SignalChip";
import { DirectionBadge } from "./ui";

export const hitKey = (hit: HitOut) => `${hit.ticker}:${hit.direction}`;

interface TrendIcon {
  icon: string;
  className: string;
}

const NEUTRAL: TrendIcon = { icon: "■", className: "text-muted" };

const TREND_ICON: Record<string, TrendIcon> = {
  up: { icon: "▲", className: "text-up" },
  down: { icon: "▼", className: "text-down" },
  neutral: NEUTRAL,
};

function TrendPair({ daily, weekly }: { daily: string; weekly: string }) {
  const render = (trend: string, label: string) => {
    const style = TREND_ICON[trend] ?? NEUTRAL;
    return (
      <span className={style.className} title={`${label} trend: ${trend}`}>
        {label}
        {style.icon}
      </span>
    );
  };
  return (
    <span className="inline-flex gap-2 text-xs">
      {render(daily, "D")}
      {render(weekly, "W")}
    </span>
  );
}

function scoreTitle(hit: HitOut): string {
  const { signals, trend, weekly, relative_strength } = hit.score;
  return `signals ${fmtNumber(signals, 1)} · daily trend ${fmtNumber(trend, 1)} · weekly ${fmtNumber(weekly, 1)} · RS ${fmtNumber(relative_strength, 1)}`;
}

const columns: Column<HitOut>[] = [
  {
    key: "ticker",
    header: "Ticker",
    sortValue: (hit) => hit.ticker,
    render: (hit) => <span className="font-mono font-semibold">{hit.ticker}</span>,
  },
  {
    key: "dir",
    header: "Dir",
    sortValue: (hit) => hit.direction,
    render: (hit) => <DirectionBadge direction={hit.direction} />,
  },
  {
    key: "score",
    header: "Score",
    align: "right",
    sortValue: (hit) => hit.score.total,
    render: (hit) => (
      <span className="font-semibold" title={scoreTitle(hit)}>
        {fmtNumber(hit.score.total, 1)}
      </span>
    ),
  },
  {
    key: "signals",
    header: "Signals (bars ago)",
    sortValue: (hit) => hit.fired.length,
    wrap: true,
    render: (hit) => (
      <span className="flex min-w-56 max-w-80 flex-wrap gap-1">
        {hit.fired.map((item) => (
          <SignalChip key={item.name} name={item.name} family={item.family} barsAgo={item.bars_ago} />
        ))}
      </span>
    ),
  },
  {
    key: "close",
    header: "Close",
    align: "right",
    sortValue: (hit) => hit.close,
    render: (hit) => fmtPrice(hit.close),
  },
  {
    key: "change",
    header: "Chg",
    align: "right",
    sortValue: (hit) => hit.change_pct,
    render: (hit) => <span className={tone(hit.change_pct)}>{fmtPct(hit.change_pct, 2, true)}</span>,
  },
  {
    key: "trend",
    header: "Trend",
    title: "Daily: close vs SMA200 and SMA50 vs SMA200. Weekly: 30-week SMA.",
    render: (hit) => <TrendPair daily={hit.daily_trend} weekly={hit.weekly_trend} />,
  },
  {
    key: "rs",
    header: "RS",
    title: "Relative strength percentile within the scanned universe",
    align: "right",
    sortValue: (hit) => hit.rs_percentile,
    render: (hit) => fmtNumber(hit.rs_percentile, 0),
  },
  { key: "atr", header: "ATR", align: "right", sortValue: (hit) => hit.atr_pct, render: (hit) => fmtPct(hit.atr_pct) },
  {
    key: "stop",
    header: "Stop",
    align: "right",
    render: (hit) => <span className="text-down">{fmtPrice(hit.risk.stop)}</span>,
  },
  {
    key: "target",
    header: "Target",
    align: "right",
    render: (hit) => <span className="text-up">{fmtPrice(hit.risk.targets[0])}</span>,
  },
  {
    key: "size",
    header: "Size",
    align: "right",
    sortValue: (hit) => hit.risk.size,
    render: (hit) => fmtSize(hit.risk.size),
  },
  {
    key: "edge",
    header: "Edge",
    title:
      "Most recent signal on this ticker: win rate · average return after the edge horizon, event count, and the average minus the average of all bars.",
    align: "right",
    sortValue: (hit) => hit.edge?.edge,
    render: (hit) =>
      hit.edge && hit.edge.events > 0 ? (
        <span className="inline-flex flex-col items-end leading-tight">
          <span>
            {fmtNumber(hit.edge.win_rate, 0)}% ·{" "}
            <span className={tone(hit.edge.mean_return)}>{fmtPct(hit.edge.mean_return, 2, true)}</span>
          </span>
          <span className="text-xs text-muted">
            n={hit.edge.events} · vs base <span className={tone(hit.edge.edge)}>{fmtSigned(hit.edge.edge)}</span>
          </span>
        </span>
      ) : (
        <span className="text-muted">no history</span>
      ),
  },
];

export function HitsTable({
  hits,
  onSelect,
  selectedKey,
}: {
  hits: HitOut[];
  onSelect: (hit: HitOut) => void;
  selectedKey: string | null;
}) {
  return (
    <DataTable
      rows={hits}
      columns={columns}
      rowKey={hitKey}
      onRowClick={onSelect}
      selectedKey={selectedKey}
      initialSort={{ key: "score", direction: "desc" }}
      caption="Scan results"
    />
  );
}
