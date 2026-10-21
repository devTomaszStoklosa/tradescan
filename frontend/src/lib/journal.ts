/**
 * The trade journal's form: a trade as typed and the request it becomes. The server checks what depends on more
 * than one field (the stop's side of the entry, an exit with both its date and its price) and says what is wrong.
 */
import type { Direction, JournalTradeIn, JournalTradeOut, SuggestingRun } from "../api/client";
import { asSetup, type PinnedRun } from "./runs";
import { decodeSuggestingRun, suggestingRun } from "./runsFile";

export interface TradeForm {
  ticker: string;
  direction: Direction;
  /** YYYY-MM-DD, as a date input gives it. */
  opened: string;
  entryPrice: number | null;
  quantity: number | null;
  /** The initial stop, which sets the risk of 1R. */
  stop: number | null;
  /** Empty while the trade is open. */
  closed: string;
  exitPrice: number | null;
  fees: number | null;
  notes: string;
  /** A copy of the pinned run that suggested the trade. */
  run: SuggestingRun | null;
}

const pad = (value: number) => String(value).padStart(2, "0");

/** Today in the browser's time zone, as YYYY-MM-DD. */
export const today = (now = new Date()): string =>
  `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

/** A new trade opened today; from a pinned run, with its copy, its direction and the ticker it tested. */
export function newTradeForm(run?: PinnedRun, now = new Date()): TradeForm {
  return {
    ticker: run?.kind === "backtest" ? run.ticker : "",
    // A rotation only buys.
    direction: (run && asSetup(run)?.direction) ?? "long",
    opened: today(now),
    entryPrice: null,
    quantity: null,
    stop: null,
    closed: "",
    exitPrice: null,
    fees: null,
    notes: "",
    run: run ? suggestingRun(run) : null,
  };
}

export function tradeFormOf(trade: JournalTradeOut): TradeForm {
  return {
    ticker: trade.ticker,
    direction: trade.direction,
    opened: trade.opened,
    entryPrice: trade.entry_price,
    quantity: trade.quantity,
    stop: trade.stop ?? null,
    closed: trade.closed ?? "",
    exitPrice: trade.exit_price ?? null,
    fees: trade.fees || null,
    notes: trade.notes,
    run: trade.run ?? null,
  };
}

/** The request for the form; null until the ticker, the entry date and price and the quantity are filled in. */
export function tradeBody(form: TradeForm): JournalTradeIn | null {
  const ticker = form.ticker.trim().toUpperCase();
  if (!ticker || !form.opened || form.entryPrice === null || form.quantity === null) return null;
  return {
    ticker,
    direction: form.direction,
    opened: form.opened,
    entry_price: form.entryPrice,
    quantity: form.quantity,
    stop: form.stop,
    closed: form.closed || null,
    exit_price: form.exitPrice,
    fees: form.fees ?? 0,
    notes: form.notes.trim(),
    run: form.run,
  };
}

/** The run a trade keeps, or the reason it cannot be shown. */
export function suggestedBy(run: SuggestingRun): { run: PinnedRun } | { problem: string } {
  try {
    return { run: decodeSuggestingRun(run) };
  } catch (problem) {
    return { problem: problem instanceof Error ? problem.message : String(problem) };
  }
}
