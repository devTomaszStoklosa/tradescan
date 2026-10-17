/** Holdings, exposure, turnover and costs of a momentum rotation, by period. */
import { useMemo, type ReactNode } from "react";

import type { RotationStatsOut } from "../api/client";
import { DASH, fmtNumber, fmtPct } from "../lib/format";
import { DataTable, type Column } from "./DataTable";

interface RotationStat {
  key: keyof RotationStatsOut;
  label: string;
  format: (stats: RotationStatsOut) => string;
}

const STATS: RotationStat[] = [
  { key: "rebalances", label: "Rebalances", format: (s) => String(s.rebalances) },
  { key: "average_holdings", label: "Average holdings", format: (s) => fmtNumber(s.average_holdings, 2) },
  { key: "max_holdings", label: "Most holdings", format: (s) => String(s.max_holdings) },
  { key: "average_exposure_pct", label: "Average invested", format: (s) => fmtPct(s.average_exposure_pct) },
  { key: "average_safe_pct", label: "Average in the safe asset", format: (s) => fmtPct(s.average_safe_pct) },
  { key: "average_cash_pct", label: "Average in cash", format: (s) => fmtPct(s.average_cash_pct) },
  { key: "turnover_pct", label: "Turnover per year", format: (s) => fmtPct(s.turnover_pct, 0) },
  { key: "orders", label: "Orders filled", format: (s) => String(s.orders) },
  { key: "unfilled_orders", label: "Orders dropped: no bar before the next rebalance", format: (s) => String(s.unfilled_orders) },
  { key: "commissions", label: "Commissions", format: (s) => fmtNumber(s.commissions, 0) },
];

export interface RotationStatsColumn {
  key: string;
  header: ReactNode;
  /** Null shows dashes, for a period the run does not have. */
  stats: RotationStatsOut | null;
}

/** One row per stat, one column per period. */
export function RotationStatsTable({ columns, caption }: { columns: RotationStatsColumn[]; caption: string }) {
  const tableColumns = useMemo<Column<RotationStat>[]>(
    () => [
      { key: "stat", header: "Rotation", render: (row) => <span className="text-muted">{row.label}</span> },
      ...columns.map(({ key, header, stats }) => ({
        key,
        header,
        align: "right" as const,
        render: (row: RotationStat) => (stats ? row.format(stats) : DASH),
      })),
    ],
    [columns],
  );
  return <DataTable rows={STATS} columns={tableColumns} rowKey={(row) => row.key} caption={caption} dense />;
}
