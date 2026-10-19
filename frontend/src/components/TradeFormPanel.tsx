import { useEffect, useState, type SubmitEvent } from "react";

import type { Direction, JournalTradeIn } from "../api/client";
import { suggestedBy, tradeBody, type TradeForm } from "../lib/journal";
import type { PinnedRun } from "../lib/runs";
import { suggestingRun } from "../lib/runsFile";
import { Button, Field, Input, NumberInput, Panel, Select, TextArea } from "./ui";

const NONE = "none";
/** The copy the trade already keeps, which may no longer be pinned. */
const KEPT = "kept";
const pinChoice = (run: PinnedRun) => `pin:${run.id}`;

function keptLabel(form: TradeForm): string {
  if (!form.run) return "";
  const shown = suggestedBy(form.run);
  return "run" in shown ? `${shown.run.name} (as logged)` : "The logged run (unreadable)";
}

/** Logs a new trade or edits one; `editing` keeps the trade's own copy of its run on offer. */
export function TradeFormPanel({
  initial,
  editing,
  runs,
  busy,
  onSubmit,
  onCancel,
}: {
  initial: TradeForm;
  editing: boolean;
  runs: PinnedRun[];
  busy: boolean;
  onSubmit: (body: JournalTradeIn) => void;
  onCancel?: () => void;
}) {
  const choiceOf = (form: TradeForm) => {
    if (!form.run) return NONE;
    const pinned = runs.find((run) => run.id === form.run?.snapshot.id);
    return !editing && pinned ? pinChoice(pinned) : KEPT;
  };
  const [draft, setDraft] = useState(initial);
  const [choice, setChoice] = useState(() => choiceOf(initial));
  useEffect(() => {
    setDraft(initial);
    setChoice(choiceOf(initial));
    // Only another trade to fill in resets the form; pinning or renaming a run meanwhile does not.
  }, [initial]);
  const body = tradeBody(draft);
  const set = <K extends keyof TradeForm>(key: K, value: TradeForm[K]) => setDraft({ ...draft, [key]: value });

  const choose = (value: string) => {
    setChoice(value);
    const pinned = runs.find((run) => pinChoice(run) === value);
    set("run", value === KEPT ? initial.run : pinned ? suggestingRun(pinned) : null);
  };

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (body) onSubmit(body);
  };

  return (
    <Panel>
      <form onSubmit={submit} noValidate className="space-y-3">
        <h2 className="text-sm font-semibold">{editing ? "Edit trade" : "Log a trade"}</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          <Field label="Ticker">
            <Input
              value={draft.ticker}
              onChange={(event) => set("ticker", event.target.value)}
              placeholder="AAPL"
              autoCapitalize="characters"
            />
          </Field>
          <Field label="Direction">
            <Select value={draft.direction} onChange={(event) => set("direction", event.target.value as Direction)}>
              <option value="long">Long</option>
              <option value="short">Short</option>
            </Select>
          </Field>
          <Field label="Entry date">
            <Input type="date" value={draft.opened} onChange={(event) => set("opened", event.target.value)} />
          </Field>
          <Field label="Entry price">
            <NumberInput value={draft.entryPrice} min={0} onChange={(value) => set("entryPrice", value)} />
          </Field>
          <Field label="Quantity">
            <NumberInput value={draft.quantity} min={0} onChange={(value) => set("quantity", value)} />
          </Field>
          <Field label="Initial stop" hint="Sets 1R">
            <NumberInput value={draft.stop} min={0} onChange={(value) => set("stop", value)} />
          </Field>
          <Field label="Exit date" hint="Empty while open">
            <Input type="date" value={draft.closed} onChange={(event) => set("closed", event.target.value)} />
          </Field>
          <Field label="Exit price">
            <NumberInput value={draft.exitPrice} min={0} onChange={(value) => set("exitPrice", value)} />
          </Field>
          <Field label="Fees" hint="Entry and exit together">
            <NumberInput value={draft.fees} min={0} placeholder="0" onChange={(value) => set("fees", value)} />
          </Field>
          <div className="col-span-2 sm:col-span-3">
            <Field label="Suggested by" hint="A copy is kept, so unpinning the run does not remove it">
              <Select value={choice} onChange={(event) => choose(event.target.value)}>
                <option value={NONE}>No pinned run</option>
                {editing && initial.run && <option value={KEPT}>{keptLabel(initial)}</option>}
                {runs.map((run) => (
                  <option key={run.id} value={pinChoice(run)}>
                    #{run.slot} {run.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </div>
        <Field label="Notes">
          <TextArea
            rows={3}
            value={draft.notes}
            maxLength={10_000}
            onChange={(event) => set("notes", event.target.value)}
            placeholder="Why you took it, what you saw, what you would do differently"
          />
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" variant="primary" disabled={busy || !body}>
            {busy ? "Saving…" : editing ? "Save trade" : "Log trade"}
          </Button>
          {onCancel && (
            <Button variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          )}
        </div>
      </form>
    </Panel>
  );
}
