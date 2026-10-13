import { createContext, useContext, useMemo, type ReactNode } from "react";

import type { AccountIn } from "../api/client";
import { useStoredState } from "../lib/storage";

/** `null` means "use the server default from settings.toml". */
export interface Account {
  equity: number | null;
  riskPct: number | null;
  lotSize: number | null;
}

const EMPTY: Account = { equity: null, riskPct: null, lotSize: null };

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

export function toAccountIn(account: Account): AccountIn {
  return { equity: account.equity, risk_pct: account.riskPct, lot_size: account.lotSize };
}
