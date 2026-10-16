/** Open positions, exposure and skipped signals of a portfolio: by period for one run, and for pinned runs side by side. */
import { useMemo, type ReactNode } from "react";

import type { PortfolioStatsOut } from "../api/client";
import { DASH, fmtNumber, fmtPct } from "../lib/format";
import { DataTable, type Column } from "./DataTable";

interface PortfolioStat {
  key: keyof PortfolioStatsOut;
  label: string;
  format: (stats: PortfolioStatsOut) => string;
}

const STATS: PortfolioStat[] = [
  { key: "average_positions", label: "Average open positions", format: (s) => fmtNumber(s.average_positions, 2) },
  { key: "max_positions", label: "Most open positions", format: (s) => String(s.max_positions) },
  { key: "average_exposure_pct", label: "Average gross exposure", format: (s) => fmtPct(s.average_exposure_pct) },
  { key: "max_exposure_pct", label: "Highest gross exposure", format: (s) => fmtPct(s.max_exposure_pct) },
  { key: "orders", label: "Entry orders", format: (s) => String(s.orders) },
  { key: "skipped_no_slot", label: "Signals skipped: no free slot", format: (s) => String(s.skipped_no_slot) },
  { key: "skipped_no_room", label: "Signals skipped: no exposure room", format: (s) => String(s.skipped_no_room) },
];

export interface StatsColumn {
  key: string;
  header: ReactNode;
  /** Null shows dashes, for a period the run does not have. */
  stats: PortfolioStatsOut | null;
}

/** One row per stat, one column per period or run. */
export function PortfolioStatsTable({ columns, caption }: { columns: StatsColumn[]; caption: string }) {
  const tableColumns = useMemo<Column<PortfolioStat>[]>(
    () => [
      { key: "stat", header: "Portfolio", render: (row) => <span className="text-muted">{row.label}</span> },
      ...columns.map(({ key, header, stats }) => ({
        key,
        header,
        align: "right" as const,
        render: (row: PortfolioStat) => (stats ? row.format(stats) : DASH),
      })),
    ],
    [columns],
  );
  return <DataTable rows={STATS} columns={tableColumns} rowKey={(row) => row.key} caption={caption} dense />;
}
