import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { config, signals, watchlistResult, watchlists } from "../test/fixtures";
import { WatchlistPage } from "./WatchlistPage";
import { requestBody, requestUrl } from "../test/fetch";

const RESPONSES: Record<string, unknown> = {
  "/config": config,
  "/signals": signals,
  "/watchlists": watchlists,
  "/watchlist-backtest": watchlistResult,
};

function renderPage(path: string) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = requestUrl(input);
    const body = Object.entries(RESPONSES).find(([route]) => url.endsWith(route))?.[1] ?? null;
    return new Response(JSON.stringify(body), {
      status: body ? 200 : 404,
      headers: { "Content-Type": "application/json" },
    });
  });
  const router = createMemoryRouter(
    [
      { path: "/watchlist", element: <WatchlistPage /> },
      { path: "/backtest", element: <p>backtest page</p> },
    ],
    { initialEntries: [path] },
  );
  render(
    <AccountProvider>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </AccountProvider>,
  );
  return router;
}

const bodies = () =>
  vi
    .mocked(globalThis.fetch)
    .mock.calls.filter(([input]) => requestUrl(input).endsWith("/watchlist-backtest"))
    .map(([, init]) => requestBody(init) as Record<string, unknown>);

const RESULT_URL = "/watchlist?w=us_large&signal=connors_rsi2_long&filter=market";

describe("WatchlistPage", () => {
  it("runs a setup on the default watchlist without asking for a ticker", async () => {
    localStorage.setItem("tradescan.account", JSON.stringify({ equity: 50000, riskPct: null, lotSize: null }));
    const router = renderPage("/watchlist");
    await screen.findByRole("button", { name: "Run on every ticker" });
    expect(screen.queryByLabelText("Ticker")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Universe" })).toHaveValue("us_large");
    expect(screen.getByRole("button", { name: "Run on every ticker" })).toBeDisabled();
    expect(screen.getByLabelText("Max units")).toBeInTheDocument(); // every ticker's backtest can pyramid

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Signal" }), "connors_rsi2_long");
    await userEvent.click(screen.getByRole("button", { name: "Run on every ticker" }));

    await waitFor(() => expect(router.state.location.search).toBe("?w=us_large&signal=connors_rsi2_long"));
    await waitFor(() =>
      expect(bodies().at(-1)).toMatchObject({
        watchlist: "us_large",
        signal: "connors_rsi2_long",
        settings: { account: { equity: 50000 } },
      }),
    );
    expect(bodies().at(-1)).not.toHaveProperty("ticker");
    localStorage.clear();
  });

  it("shows the spread, the pooled trades and every ticker linked to its backtest", async () => {
    renderPage(RESULT_URL);
    expect(await screen.findByText("No data for: TSLA")).toBeInTheDocument();
    expect(screen.getByText(/2 tickers on the vectorized engine · each split at its own last 30%/)).toBeInTheDocument();
    expect(screen.getByText(/^Filters: Benchmark close above its SMA\(200\).* · benchmark SPY$/)).toBeInTheDocument();
    expect(screen.getByText("+0.40 R → -0.10 R")).toBeInTheDocument(); // median expectancy, in-sample → out-of-sample
    expect(screen.getByText("1 of 2")).toBeInTheDocument(); // MSFT has 6 trades

    const spread = screen.getByRole("table", { name: "Spread of Expectancy across tickers" });
    expect(within(spread).getAllByRole("row")[1]).toHaveTextContent(
      "Full history2+0.30 R+0.35 R+0.40 R+0.45 R+0.50 R100%",
    );

    const pooled = screen.getByRole("table", { name: "All tickers' trades pooled, by period" });
    expect(within(pooled).getAllByRole("row")[3]).toHaveTextContent("Out-of-sample11241.7%-0.10 R0.80-0.40");

    const tickers = screen.getByRole("table", { name: "Every ticker's Expectancy" });
    const rows = within(tickers).getAllByRole("row");
    expect(rows[1]).toHaveTextContent(/^MSFT6\+0\.50 R––/); // best full-history expectancy first, no split
    expect(within(rows[2]!).getByRole("link", { name: "AAPL" })).toHaveAttribute(
      "href",
      "/backtest?ticker=AAPL&signal=connors_rsi2_long&eng=vectorized&filter=market&b=SPY",
    );
  });

  it("ranks by another metric without running again", async () => {
    const router = renderPage(RESULT_URL);
    await screen.findByRole("table", { name: "Every ticker's Expectancy" });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Rank by" }), "profit_factor");
    expect(router.state.location.search).toContain("m=profit_factor");
    const spread = screen.getByRole("table", { name: "Spread of Profit factor across tickers" });
    expect(within(spread).getAllByRole("row")[1]).toHaveTextContent("Full history21.601.60∞∞∞100%");
    expect(bodies()).toHaveLength(1);
  });
});
