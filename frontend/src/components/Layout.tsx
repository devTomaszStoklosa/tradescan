import { NavLink, Outlet } from "react-router";

import { usePinnedRuns } from "../state/pinnedRuns";
import { AccountMenu } from "./AccountMenu";
import { ThemeToggle } from "./ThemeToggle";

const LINKS = [
  { to: "/", label: "Scanner", end: true },
  { to: "/backtest", label: "Backtest", end: false },
  { to: "/sweep", label: "Sweep", end: false },
  { to: "/walk-forward", label: "Walk-forward", end: false },
  { to: "/watchlist", label: "Watchlist", end: false },
  { to: "/portfolio", label: "Portfolio", end: false },
  { to: "/rotation", label: "Rotation", end: false },
  { to: "/rotation-sweep", label: "Rotation sweep", end: false },
  { to: "/edge", label: "Edge", end: false },
  { to: "/compare", label: "Compare", end: false },
  { to: "/journal", label: "Journal", end: false },
  { to: "/signals", label: "Signals", end: false },
];

export function Layout() {
  const pinned = usePinnedRuns().runs.length;
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-panel/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
          <NavLink to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <img src="/favicon.svg" alt="" className="size-6" />
            tradescan
          </NavLink>
          <nav
            aria-label="Main"
            className="order-last -mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto sm:flex-1"
          >
            {LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-1.5 text-sm whitespace-nowrap transition ${isActive ? "bg-panel-2 font-medium text-fg" : "text-muted hover:text-fg"}`
                }
              >
                {link.label}
                {link.to === "/compare" && pinned > 0 && (
                  <span className="num ml-1.5 rounded-full bg-accent/15 px-1.5 text-xs text-accent">
                    {pinned}
                    <span className="sr-only"> pinned</span>
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <AccountMenu />
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 space-y-4 px-4 py-5">
        <Outlet />
      </main>
      <footer className="border-t border-line px-4 py-3 text-center text-xs text-muted">
        Research tool, not investment advice. Prices from Yahoo Finance via yfinance; charts by TradingView Lightweight
        Charts.
      </footer>
    </div>
  );
}
