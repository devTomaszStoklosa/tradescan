import type { CSSProperties } from "react";

import type { EdgeRowOut, EdgeStatsOut } from "../api/client";
import { fmtNumber, fmtPct } from "../lib/format";
import { DataTable, type Column } from "./DataTable";
import { SignalChip } from "./SignalChip";
import { DirectionBadge } from "./ui";

/** Background tint grows with the size of the edge, capped so text stays readable. */
function heatStyle(edge: number | null | undefined): CSSProperties | undefined {
  if (edge === null || edge === undefined || edge === 0) return undefined;
  const intensity = Math.min(Math.abs(edge) * 25, 35);
  return { "--heat": intensity, "--heat-color": edge > 0 ? "var(--up)" : "var(--down)" } as CSSProperties;
}

const statAt = (row: EdgeRowOut, index: number): EdgeStatsOut | undefined => row.stats[index];

export function EdgeTable({ rows, horizons, minEvents = 0 }: { rows: EdgeRowOut[]; horizons: number[]; minEvents?: number }) {
  const columns: Column<EdgeRowOut>[] = [
    {
      key: "signal",
      header: "Signal",
      sortValue: (row) => row.signal,
      render: (row) => (
        <span title={row.description}>
          <SignalChip name={row.signal} family={row.family} />
        </span>
      ),
    },
    { key: "dir", header: "Dir", sortValue: (row) => row.direction, render: (row) => <DirectionBadge direction={row.direction} /> },
    ...horizons.flatMap((horizon, index): Column<EdgeRowOut>[] => [
      {
        key: `n${horizon}`,
        header: `N ${horizon}d`,
        align: "right",
        sortValue: (row) => statAt(row, index)?.events,
        render: (row) => {
          const events = statAt(row, index)?.events ?? 0;
          return <span className={events < Math.max(minEvents, 20) ? "text-warn" : "text-muted"}>{events}</span>;
        },
      },
      {
        key: `win${horizon}`,
        header: `Win ${horizon}d`,
        align: "right",
        sortValue: (row) => statAt(row, index)?.win_rate,
        render: (row) => fmtPct(statAt(row, index)?.win_rate, 0),
      },
      {
        key: `avg${horizon}`,
        header: `Avg ${horizon}d`,
        align: "right",
        sortValue: (row) => statAt(row, index)?.mean_return,
        render: (row) => fmtPct(statAt(row, index)?.mean_return, 2, true),
      },
      {
        key: `edge${horizon}`,
        header: `vs base ${horizon}d`,
        title: "Average return after the signal minus the average return of entering on any bar",
        align: "right",
        sortValue: (row) => statAt(row, index)?.edge,
        render: (row) => {
          const edge = statAt(row, index)?.edge;
          return (
            <span className="heat -mx-1.5 rounded px-1.5 py-0.5 font-medium" style={heatStyle(edge)}>
              {fmtNumber(edge, 2)}
            </span>
          );
        },
      },
    ]),
  ];
  const middle = horizons[Math.floor(horizons.length / 2)];
  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => row.signal}
      dense
      initialSort={middle !== undefined ? { key: `edge${middle}`, direction: "desc" } : undefined}
      caption="Signal edge by horizon"
    />
  );
}
