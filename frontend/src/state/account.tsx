import { createContext, useContext, useMemo, type ReactNode } from "react";

import { useStoredState } from "../lib/storage";
import type { Overrides, Values } from "../lib/overrides";

/** `null` (or missing, in data saved by older versions) means "use the server default from settings.toml". */
export interface Account {
  equity: number | null;
  riskPct: number | null;
  maxPositionPct?: number | null;
  lotSize: number | null;
}

const EMPTY: Account = { equity: null, riskPct: null, maxPositionPct: null, lotSize: null };

interface AccountValue {
  account: Account;
  setAccount: (account: Account) => void;
  reset: () => void;
}

const AccountContext = createContext<AccountValue | null>(null);

export function AccountProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useStoredState<Account>("tradescan.account", EMPTY);
  const value = useMemo(() => ({ account, setAccount, reset: () => setAccount(EMPTY) }), [account, setAccount]);
  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}

export function useAccount(): AccountValue {
  const value = useContext(AccountContext);
  if (!value) throw new Error("useAccount must be used inside AccountProvider");
  return value;
}

/** The account as overrides of the `account` settings section, keyed by the API's parameter names. */
export function accountValues(account: Account): Values {
  const entries: [string, number | null | undefined][] = [
    ["equity", account.equity],
    ["risk_pct", account.riskPct],
    ["max_position_pct", account.maxPositionPct],
    ["lot_size", account.lotSize],
  ];
  return Object.fromEntries(entries.filter((entry): entry is [string, number] => typeof entry[1] === "number"));
}

/** Request settings: the form's overrides plus the account saved in this browser. */
export function withAccount(settings: Overrides, account: Account): Overrides {
  const values = { ...settings.account, ...accountValues(account) };
  return Object.keys(values).length ? { ...settings, account: values } : settings;
}
