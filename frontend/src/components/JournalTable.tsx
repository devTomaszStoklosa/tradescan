import { useMemo } from "react";
import { Link } from "react-router";

import type { JournalTradeOut, SuggestingRun } from "../api/client";
import { DASH, fmtPct, fmtPrice, fmtSigned, fmtSize, tone } from "../lib/format";
import { suggestedBy } from "../lib/journal";
import { runSubject } from "../lib/runs";
import { DataTable, type Column } from "./DataTable";
import { openRun } from "./RunCard";
import { Button, DirectionBadge } from "./ui";

/** The run that suggested a trade, with its backtest's win rate and expectancy next to the real result. */
function SuggestedByCell({ copy }: { copy: SuggestingRun }) {
  const shown = useMemo(() => suggestedBy(copy), [copy]);
  if (!("run" in shown)) return <span className="text-xs text-down">Run could not be read ({shown.problem})</span>;
  const { run } = shown;
  const open = openRun(run);
  return (
    <div className="space-y-0.5">
      <div className="font-medium">{run.name}</div>
      <div className="num text-xs text-muted">
        {runSubject(run)} · {fmtPct(run.metrics.win_rate_pct, 0)} wins · {fmtSigned(run.metrics.expectancy_r)} R per trade · {run.metrics.trades} trades
      </div>
      <Link to={open.to} className="text-xs text-accent hover:underline">
        {open.label}
      </Link>
    </div>
  );
}

export function JournalTable({
  trades,
  onEdit,
  onDelete,
}: {
  trades: JournalTradeOut[];
  onEdit: (trade: JournalTradeOut) => void;
  onDelete: (trade: JournalTradeOut) => void;
}) {
  const columns = useMemo<Column<JournalTradeOut>[]>(
    () => [
      { key: "opened", header: "Opened", render: (trade) => <span className="num">{trade.opened}</span>, sortValue: (trade) => trade.opened },
      {
        key: "ticker",
        header: "Ticker",
        render: (trade) => (
          <span className="inline-flex items-center gap-1.5">
            <span className="font-mono font-semibold">{trade.ticker}</span>
            <DirectionBadge direction={trade.direction} />
          </span>
        ),
        sortValue: (trade) => trade.ticker,
      },
      { key: "quantity", header: "Qty", align: "right", render: (trade) => fmtSize(trade.quantity) },
      { key: "entry", header: "Entry", align: "right", render: (trade) => fmtPrice(trade.entry_price) },
      { key: "stop", header: "Stop", align: "right", render: (trade) => fmtPrice(trade.stop) },
      {
        key: "exit",
        header: "Exit",
        align: "right",
        render: (trade) =>
          trade.is_open ? (
            <span className="text-muted">open</span>
          ) : (
            <span>
              {fmtPrice(trade.exit_price)} <span className="text-xs text-muted">{trade.closed}</span>
            </span>
          ),
        sortValue: (trade) => trade.closed ?? null,
      },
      {
        key: "profit",
        header: "Profit",
        title: "After fees, in the ticker's currency",
        align: "right",
        render: (trade) => <span className={tone(trade.profit)}>{fmtSigned(trade.profit)}</span>,
        sortValue: (trade) => trade.profit,
      },
      {
        key: "return",
        header: "Return",
        align: "right",
        render: (trade) => <span className={tone(trade.return_pct)}>{fmtPct(trade.return_pct, 2, true)}</span>,
        sortValue: (trade) => trade.return_pct,
      },
      {
        key: "r",
        header: "R",
        title: "Profit after fees in units of the initial risk",
        align: "right",
        render: (trade) => <span className={tone(trade.r_multiple)}>{trade.r_multiple === null ? DASH : `${fmtSigned(trade.r_multiple)} R`}</span>,
        sortValue: (trade) => trade.r_multiple,
      },
      { key: "run", header: "Suggested by", wrap: true, render: (trade) => (trade.run ? <SuggestedByCell copy={trade.run} /> : <span className="text-muted">{DASH}</span>) },
      { key: "notes", header: "Notes", wrap: true, className: "min-w-48 text-xs", render: (trade) => <span className="whitespace-pre-line">{trade.notes}</span> },
      {
        key: "actions",
        header: <span className="sr-only">Actions</span>,
        render: (trade) => (
          <span className="inline-flex gap-1">
            <Button aria-label={`Edit the ${trade.ticker} trade of ${trade.opened}`} onClick={() => onEdit(trade)}>
              Edit
            </Button>
            <Button variant="ghost" aria-label={`Delete the ${trade.ticker} trade of ${trade.opened}`} onClick={() => onDelete(trade)}>
              Delete
            </Button>
          </span>
        ),
      },
    ],
    [onEdit, onDelete],
  );
  return <DataTable rows={trades} columns={columns} rowKey={(trade) => String(trade.id)} caption="Trades in the journal" dense />;
}
