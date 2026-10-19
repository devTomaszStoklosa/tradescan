import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api, type JournalSummaryOut, type JournalTradeIn, type JournalTradeOut } from "../api/client";
import { JOURNAL_KEY, useJournal } from "../api/hooks";
import { JournalTable } from "../components/JournalTable";
import { TradeFormPanel } from "../components/TradeFormPanel";
import { EmptyState, ErrorBox, Loading, PageHeader, StatTile } from "../components/ui";
import { DASH, fmtPct, fmtSigned, tone } from "../lib/format";
import { newTradeForm, tradeFormOf } from "../lib/journal";
import { usePinnedRuns } from "../state/pinnedRuns";

const FORM_ID = "journal-form";

const fmtR = (value: number | null) => (value === null ? DASH : `${fmtSigned(value)} R`);

function SummaryTiles({ summary }: { summary: JournalSummaryOut }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <StatTile label="Open trades" value={summary.open_trades} />
      <StatTile label="Closed trades" value={summary.closed_trades} />
      <StatTile label="Win rate" value={fmtPct(summary.win_rate_pct)} sub="profit after fees" />
      <StatTile
        label="Average return"
        value={fmtPct(summary.average_return_pct, 2, true)}
        valueClass={tone(summary.average_return_pct)}
      />
      <StatTile
        label="Average R"
        value={fmtR(summary.average_r)}
        valueClass={tone(summary.average_r)}
        sub={`${summary.r_trades} with a stop`}
      />
      <StatTile label="Total R" value={fmtR(summary.total_r)} valueClass={tone(summary.total_r)} />
    </div>
  );
}

export function JournalPage() {
  const [params, setParams] = useSearchParams();
  const journal = useJournal();
  const pinned = usePinnedRuns();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<JournalTradeOut | null>(null);
  // Bumped after a save, so the form starts over.
  const [round, setRound] = useState(0);
  const runId = params.get("run");

  // A fresh form only for another trade to edit, another run to log from or after a save: runs that reload
  // when the tab regains focus must not wipe what is typed.
  const initial = useMemo(
    () => (editing ? tradeFormOf(editing) : newTradeForm(pinned.runs.find((run) => run.id === runId))),
    // The runs themselves are left out on purpose; `loading` is in, so the run is found once the runs arrive.
    [editing, runId, pinned.loading, round],
  );

  const refresh = () => void queryClient.invalidateQueries({ queryKey: JOURNAL_KEY });
  const save = useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: JournalTradeIn }) =>
      id === null ? api.logTrade(body) : api.replaceTrade(id, body),
    onSuccess: () => {
      refresh();
      setEditing(null);
      setRound((value) => value + 1);
      if (runId) setParams({}, { replace: true });
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteTrade(id),
    onSuccess: (_, id) => {
      refresh();
      if (editing?.id === id) setEditing(null);
    },
  });

  const edit = (trade: JournalTradeOut) => {
    save.reset();
    setEditing(trade);
    document.getElementById(FORM_ID)?.scrollIntoView?.({ behavior: "smooth" });
  };
  const onDelete = (trade: JournalTradeOut) => {
    if (window.confirm(`Delete the ${trade.ticker} trade of ${trade.opened}? This cannot be undone.`))
      remove.mutate(trade.id);
  };

  return (
    <>
      <PageHeader
        title="Journal"
        subtitle="Your real trades with notes and the pinned run that suggested each, kept on the tradescan server."
      />
      <div id={FORM_ID}>
        <TradeFormPanel
          initial={initial}
          editing={editing !== null}
          runs={pinned.runs}
          busy={save.isPending}
          onSubmit={(body) => save.mutate({ id: editing?.id ?? null, body })}
          onCancel={
            editing
              ? () => {
                  save.reset();
                  setEditing(null);
                }
              : undefined
          }
        />
      </div>
      {save.isError && <ErrorBox error={save.error} />}
      {remove.isError && <ErrorBox error={remove.error} />}
      {journal.isLoading && <Loading message="Loading the journal…" />}
      {journal.isError && <ErrorBox error={journal.error} onRetry={() => journal.refetch()} />}
      {journal.data && (
        <div className="space-y-3">
          <SummaryTiles summary={journal.data.summary} />
          {journal.data.trades.length ? (
            <JournalTable trades={journal.data.trades} onEdit={edit} onDelete={onDelete} />
          ) : (
            <EmptyState title="No trades logged yet">
              Fill in the form above, or press <strong>Log a trade</strong> on a run pinned in{" "}
              <Link to="/compare" className="text-accent hover:underline">
                Compare
              </Link>{" "}
              to keep the backtest that suggested it.
            </EmptyState>
          )}
          <p className="text-xs text-muted">
            Profit is in each ticker's currency, so the summary adds up returns and R multiples only. R needs the
            initial stop. The backtest next to a trade is the pinned run as it was when the trade was logged.
          </p>
        </div>
      )}
    </>
  );
}
