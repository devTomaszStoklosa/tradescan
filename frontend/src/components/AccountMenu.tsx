import { useEffect, useRef, useState } from "react";

import { useConfig } from "../api/hooks";
import { fmtCompact, fmtNumber } from "../lib/format";
import { useAccount, type Account } from "../state/account";
import { Button, Field, NumberInput } from "./ui";

/** Account size and risk used for position sizing; stored in this browser only. */
export function AccountMenu() {
  const { account, setAccount, reset } = useAccount();
  const config = useConfig();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Account>(account);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(account);
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    const onClick = (event: MouseEvent) => {
      if (panel.current && !panel.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open, account]);

  const defaults = config.data?.account;
  const equity = account.equity ?? defaults?.equity;
  const riskPct = account.riskPct ?? defaults?.risk_pct;

  return (
    <div className="relative" ref={panel}>
      <Button onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="dialog" title="Account size and risk per trade">
        <span className="num">
          {fmtCompact(equity)} · {fmtNumber(riskPct, 1)}%
        </span>
      </Button>
      {open && (
        <div
          role="dialog"
          aria-label="Account settings"
          className="absolute right-0 z-40 mt-2 w-72 max-w-[calc(100vw-2rem)] space-y-3 rounded-xl border border-line bg-panel p-4 shadow-xl"
        >
          <p className="text-xs text-muted">Used for position sizing in scans and backtests. Empty fields use the server defaults.</p>
          <Field label="Account equity">
            <NumberInput value={draft.equity} min={0} placeholder={fmtNumber(defaults?.equity, 0)} onChange={(equity) => setDraft({ ...draft, equity })} />
          </Field>
          <Field label="Risk per trade (%)">
            <NumberInput value={draft.riskPct} min={0} step="0.1" placeholder={fmtNumber(defaults?.risk_pct, 1)} onChange={(riskPct) => setDraft({ ...draft, riskPct })} />
          </Field>
          <Field label="Lot size" hint="1 for stocks, e.g. 0.0001 for crypto">
            <NumberInput value={draft.lotSize} min={0} placeholder={fmtNumber(defaults?.lot_size, 0)} onChange={(lotSize) => setDraft({ ...draft, lotSize })} />
          </Field>
          <div className="flex justify-between gap-2">
            <Button
              variant="ghost"
              onClick={() => {
                reset();
                setOpen(false);
              }}
            >
              Reset
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setAccount(draft);
                setOpen(false);
              }}
            >
              Save
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
