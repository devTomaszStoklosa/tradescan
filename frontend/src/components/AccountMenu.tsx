import { useEffect, useRef, useState } from "react";

import type { ParamSpecOut } from "../api/client";
import { useConfig } from "../api/hooks";
import { fmtCompact, fmtNumber } from "../lib/format";
import { problemOf } from "../lib/overrides";
import { useAccount, type Account } from "../state/account";
import { Button, Field, NumberInput } from "./ui";

/** Account fields and the parameter each one overrides in the `account` settings section. */
const FIELDS: { key: keyof Account; param: string }[] = [
  { key: "equity", param: "equity" },
  { key: "riskPct", param: "risk_pct" },
  { key: "maxPositionPct", param: "max_position_pct" },
  { key: "lotSize", param: "lot_size" },
];

const labelOf = (spec: ParamSpecOut) => (spec.unit ? `${spec.label} (${spec.unit})` : spec.label);

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

  const specs = config.data?.sections.find((section) => section.name === "account")?.params ?? [];
  const spec = (param: string) => specs.find((item) => item.name === param);
  const defaultOf = (param: string) => spec(param)?.default as number | undefined;
  const equity = account.equity ?? defaultOf("equity");
  const riskPct = account.riskPct ?? defaultOf("risk_pct");
  const invalid = FIELDS.some(({ key, param }) => {
    const fieldSpec = spec(param);
    const value = draft[key];
    return fieldSpec !== undefined && typeof value === "number" && problemOf(fieldSpec, value) !== null;
  });

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
          {FIELDS.map(({ key, param }) => {
            const fieldSpec = spec(param);
            if (!fieldSpec) return null;
            const value = draft[key] ?? null;
            const problem = typeof value === "number" ? problemOf(fieldSpec, value) : null;
            return (
              <Field key={param} label={labelOf(fieldSpec)} hint={problem ?? (fieldSpec.help || undefined)}>
                <NumberInput
                  value={value}
                  min={fieldSpec.minimum}
                  max={fieldSpec.maximum}
                  step={String(fieldSpec.step)}
                  placeholder={String(fieldSpec.default)}
                  invalid={problem !== null}
                  onChange={(next) => setDraft({ ...draft, [key]: next })}
                />
              </Field>
            );
          })}
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
              disabled={invalid}
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
