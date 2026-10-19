import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { JournalSummaryOut, JournalTradeIn, JournalTradeOut } from "../api/client";
import { suggestingRun } from "../lib/runsFile";
import { PinnedRunsProvider } from "../state/pinnedRuns";
import { makeRun } from "../test/fixtures";
import { MemoryRunStore } from "../test/runStore";
import { JournalPage } from "./JournalPage";
import { requestBody, requestUrl } from "../test/fetch";

const baseline = makeRun(1, {}, { name: "baseline" });

const SUMMARY: JournalSummaryOut = {
  open_trades: 0,
  closed_trades: 0,
  win_rate_pct: null,
  average_return_pct: null,
  r_trades: 0,
  average_r: null,
  total_r: null,
};

/** What a test logs: fees and notes may be left out, as the server allows. */
type TradeInput = Omit<JournalTradeIn, "fees" | "notes"> & Partial<Pick<JournalTradeIn, "fees" | "notes">>;

/** A trade as the server answers, with the results it derives. */
function tradeOut(id: number, body: TradeInput): JournalTradeOut {
  const sign = body.direction === "long" ? 1 : -1;
  const closed = body.exit_price != null;
  const profit = closed ? sign * (body.exit_price! - body.entry_price) * body.quantity - (body.fees ?? 0) : null;
  const risk = body.stop != null ? Math.abs(body.entry_price - body.stop) * body.quantity : null;
  return {
    ...body,
    stop: body.stop ?? null,
    closed: body.closed ?? null,
    exit_price: body.exit_price ?? null,
    fees: body.fees ?? 0,
    notes: body.notes ?? "",
    run: body.run ?? null,
    id,
    created_at: "2026-10-18T09:00:00+00:00",
    updated_at: "2026-10-18T09:00:00+00:00",
    is_open: !closed,
    risk,
    profit,
    return_pct: profit === null ? null : (profit / (body.entry_price * body.quantity)) * 100,
    r_multiple: profit === null || risk === null ? null : profit / risk,
  };
}

let trades: JournalTradeOut[] = [];
let summary: JournalSummaryOut = SUMMARY;

/** Request bodies sent to the journal, by method. */
const sent = (method: string) =>
  vi
    .mocked(globalThis.fetch)
    .mock.calls.filter(([input, init]) => requestUrl(input).includes("/journal/trades") && init?.method === method)
    .map(([input, init]) => ({
      url: requestUrl(input),
      body: init?.body ? (requestBody(init) as JournalTradeIn) : null,
    }));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function renderPage(path = "/journal", store = new MemoryRunStore([baseline])) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/journal")) return json({ trades, summary });
    if (method === "POST") {
      const body = requestBody(init) as JournalTradeIn;
      if (body.stop != null && body.stop >= body.entry_price)
        return json({ detail: "The stop of a long trade must be below the entry price" }, 400);
      trades = [tradeOut(trades.length + 1, body), ...trades];
      return json(trades[0], 201);
    }
    const id = Number(url.split("/").at(-1));
    if (method === "PUT") {
      trades = trades.map((trade) => (trade.id === id ? tradeOut(id, requestBody(init) as JournalTradeIn) : trade));
      return json(trades.find((trade) => trade.id === id));
    }
    if (method === "DELETE") {
      trades = trades.filter((trade) => trade.id !== id);
      return new Response(null, { status: 204 });
    }
    return json({ detail: "Not Found" }, 404);
  });
  const router = createMemoryRouter(
    [
      { path: "/journal", element: <JournalPage /> },
      { path: "/backtest", element: <p>backtest page</p> },
    ],
    { initialEntries: [path] },
  );
  render(
    <PinnedRunsProvider store={store}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </PinnedRunsProvider>,
  );
  return router;
}

const field = (name: RegExp) => screen.getByLabelText(name);

/** One change per field rather than one per key, so the form tests stay fast. */
const fill = (name: RegExp, value: string) => fireEvent.change(field(name), { target: { value } });

describe("JournalPage", () => {
  beforeEach(() => {
    trades = [];
    summary = SUMMARY;
  });

  it("logs a trade once the ticker, the entry and the quantity are filled in", async () => {
    renderPage();
    expect(await screen.findByText("No trades logged yet")).toBeInTheDocument();
    const log = screen.getByRole("button", { name: "Log trade" });
    expect(log).toBeDisabled();

    fill(/^Ticker/, "aapl");
    fill(/^Entry date/, "2026-03-02");
    fill(/^Entry price/, "180.5");
    fill(/^Quantity/, "10");
    fill(/^Initial stop/, "175");
    fill(/^Notes/, "Pullback to the 20-day SMA");
    await userEvent.click(log);

    await waitFor(() => expect(sent("POST")).toHaveLength(1));
    expect(sent("POST")[0]?.body).toEqual({
      ticker: "AAPL",
      direction: "long",
      opened: "2026-03-02",
      entry_price: 180.5,
      quantity: 10,
      stop: 175,
      closed: null,
      exit_price: null,
      fees: 0,
      notes: "Pullback to the 20-day SMA",
      run: null,
    });
    const table = await screen.findByRole("table", { name: "Trades in the journal" });
    expect(within(table).getByText("AAPL")).toBeInTheDocument();
    expect(within(table).getByText("open")).toBeInTheDocument();
    // The form starts over for the next trade.
    expect(field(/^Ticker/)).toHaveValue("");
  });

  it("logs a trade from a pinned run with a copy of the run", async () => {
    const router = renderPage("/journal?run=run-1");
    await waitFor(() => expect(field(/^Ticker/)).toHaveValue("SPY"));
    expect(field(/^Suggested by/)).toHaveDisplayValue("#1 baseline");
    fill(/^Entry price/, "500");
    fill(/^Quantity/, "2");
    await userEvent.click(screen.getByRole("button", { name: "Log trade" }));

    await waitFor(() => expect(sent("POST")).toHaveLength(1));
    expect(sent("POST")[0]?.body?.run).toEqual(JSON.parse(JSON.stringify(suggestingRun(baseline))));
    await waitFor(() => expect(router.state.location.search).toBe(""));
    const table = await screen.findByRole("table", { name: "Trades in the journal" });
    expect(within(table).getByText("baseline")).toBeInTheDocument();
    // The backtest's win rate and expectancy, next to the real result.
    expect(within(table).getByText("SPY · 62% wins · +0.21 R per trade · 42 trades")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "Open in Backtest" })).toHaveAttribute(
      "href",
      expect.stringMatching(/^\/backtest\?ticker=SPY/),
    );
  });

  it("shows each trade's result and the summary, closes a trade and deletes one", async () => {
    trades = [
      tradeOut(2, {
        ticker: "QQQ",
        direction: "short",
        opened: "2026-04-01",
        entry_price: 400,
        quantity: 5,
        stop: 410,
      }),
      tradeOut(1, {
        ticker: "SPY",
        direction: "long",
        opened: "2026-03-02",
        entry_price: 500,
        quantity: 2,
        stop: 490,
        run: suggestingRun(baseline),
      }),
    ];
    summary = {
      ...SUMMARY,
      open_trades: 1,
      closed_trades: 1,
      win_rate_pct: 100,
      average_return_pct: 5.8,
      r_trades: 1,
      average_r: 2.9,
      total_r: 2.9,
    };
    renderPage("/journal", new MemoryRunStore());
    const table = await screen.findByRole("table", { name: "Trades in the journal" });
    expect(screen.getByText("Total R").parentElement).toHaveTextContent("+2.90 R");

    await userEvent.click(within(table).getByRole("button", { name: "Edit the SPY trade of 2026-03-02" }));
    expect(screen.getByRole("heading", { name: "Edit trade" })).toBeInTheDocument();
    // The run is no longer pinned, but the trade keeps its copy.
    expect(field(/^Suggested by/)).toHaveDisplayValue("baseline (as logged)");
    fill(/^Exit date/, "2026-03-20");
    fill(/^Exit price/, "530");
    fill(/^Fees/, "2");
    await userEvent.click(screen.getByRole("button", { name: "Save trade" }));

    await waitFor(() => expect(sent("PUT")).toHaveLength(1));
    expect(sent("PUT")[0]).toMatchObject({
      url: "/api/journal/trades/1",
      body: {
        closed: "2026-03-20",
        exit_price: 530,
        fees: 2,
        run: JSON.parse(JSON.stringify(suggestingRun(baseline))) as unknown,
      },
    });
    const spy = await within(table).findByRole("row", { name: /SPY/ });
    expect(spy).toHaveTextContent("+58.00");
    expect(spy).toHaveTextContent("+2.90 R");
    expect(screen.getByRole("heading", { name: "Log a trade" })).toBeInTheDocument();

    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    await userEvent.click(within(table).getByRole("button", { name: "Delete the QQQ trade of 2026-04-01" }));
    expect(sent("DELETE")).toHaveLength(0);
    await userEvent.click(within(table).getByRole("button", { name: "Delete the QQQ trade of 2026-04-01" }));
    expect(confirm).toHaveBeenLastCalledWith("Delete the QQQ trade of 2026-04-01? This cannot be undone.");
    await waitFor(() => expect(screen.queryByRole("row", { name: /QQQ/ })).not.toBeInTheDocument());
    expect(sent("DELETE")[0]?.url).toBe("/api/journal/trades/2");
  });

  it("shows why the server refused a trade and keeps what was typed", async () => {
    renderPage();
    await screen.findByText("No trades logged yet");
    fill(/^Ticker/, "SPY");
    fill(/^Entry price/, "500");
    fill(/^Quantity/, "2");
    fill(/^Initial stop/, "510");
    await userEvent.click(screen.getByRole("button", { name: "Log trade" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The stop of a long trade must be below the entry price",
    );
    expect(field(/^Ticker/)).toHaveValue("SPY");
  });
});
