import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { PinnedRunsProvider } from "../state/pinnedRuns";
import { config, makePortfolioRun, portfolioResult, signals, watchlists } from "../test/fixtures";
import { PortfolioPage } from "./PortfolioPage";

vi.mock("../components/charts/EquityChart", () => ({ EquityChart: () => null }));

let result: unknown = portfolioResult;

function renderPage(path: string) {
  const responses: Record<string, unknown> = { "/config": config, "/signals": signals, "/watchlists": watchlists, "/portfolio-backtest": result };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = Object.entries(responses).find(([route]) => url.endsWith(route))?.[1] ?? null;
    return new Response(JSON.stringify(body), { status: body ? 200 : 404, headers: { "Content-Type": "application/json" } });
  });
  const router = createMemoryRouter(
    [
      { path: "/portfolio", element: <PortfolioPage /> },
      { path: "/backtest", element: <p>backtest page</p> },
      { path: "/watchlist", element: <p>watchlist page</p> },
    ],
    { initialEntries: [path] },
  );
  render(
    <AccountProvider>
      <PinnedRunsProvider>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </PinnedRunsProvider>
    </AccountProvider>,
  );
  return router;
}

const bodies = () =>
  vi
    .mocked(globalThis.fetch)
    .mock.calls.filter(([input]) => String(input).endsWith("/portfolio-backtest"))
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>);

const RESULT_URL = "/portfolio?w=us_large&signal=connors_rsi2_long&eng=vectorized&filter=market&set.portfolio.max_positions=5&prio=momentum";

describe("PortfolioPage", () => {
  it("runs a setup on the default watchlist with the portfolio's limits and priority", async () => {
    const router = renderPage("/portfolio");
    await screen.findByRole("button", { name: "Run portfolio" });
    expect(screen.queryByLabelText("Ticker")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Universe" })).toHaveValue("us_large");
    expect(screen.getByRole("combobox", { name: "Priority when more signals fire than fit" })).toHaveValue("relative_strength");
    expect(screen.getByRole("button", { name: "Run portfolio" })).toBeDisabled();

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Signal" }), "connors_rsi2_long");
    await userEvent.type(screen.getByLabelText("Max positions"), "5");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Priority when more signals fire than fit" }), "momentum");
    await userEvent.type(screen.getByLabelText("Skip (bars)"), "0");
    expect(screen.getByRole("button", { name: "Reset 3 changed" })).toBeInTheDocument(); // max positions, priority, skip
    await userEvent.click(screen.getByRole("button", { name: "Run portfolio" }));

    await waitFor(() =>
      expect(router.state.location.search).toBe(
        "?w=us_large&signal=connors_rsi2_long&eng=vectorized&set.portfolio.max_positions=5&prio=momentum&pr.momentum.skip=0",
      ),
    );
    await waitFor(() =>
      expect(bodies().at(-1)).toMatchObject({
        watchlist: "us_large",
        signal: "connors_rsi2_long",
        engines: ["vectorized"],
        priority: { name: "momentum", params: { skip: 0 } },
        settings: { portfolio: { max_positions: 5 } },
      }),
    );
    expect(bodies().at(-1)).not.toHaveProperty("ticker");
  });

  it("warns that Cerebro is slow on a large universe", async () => {
    renderPage("/portfolio?w=us_large&signal=connors_rsi2_long&eng=vectorized,cerebro");
    await screen.findByRole("button", { name: "Run portfolio" });
    const large = watchlists.find((item) => item.name === "us_large")!.tickers.length > 20;
    expect(screen.queryByText(/Cerebro checks the vectorized engine and is slow/) !== null).toBe(large);
  });

  it("shows the portfolio's metrics, stats, contributions and trades with their tickers", async () => {
    renderPage(RESULT_URL);
    expect(await screen.findByText("No data for: TSLA")).toBeInTheDocument();
    expect(screen.getByText(/2 tickers, one equity · at most 5 positions and 100% gross exposure · priority: Return from 252 bars ago to 21 bars ago/)).toBeInTheDocument();
    expect(screen.getByText("SPY buy & hold +180.5%")).toBeInTheDocument();
    expect(screen.getByText("34")).toBeInTheDocument(); // skipped signals
    expect(screen.getByText("30 without a slot, 4 without exposure room")).toBeInTheDocument();

    const metrics = screen.getByRole("table", { name: "Portfolio metrics by period" });
    expect(within(metrics).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Metric", "Full history", "In-sample", "Out-of-sample"]);
    const stats = screen.getByRole("table", { name: "Portfolio stats by period" });
    expect(within(stats).getByText("Entry orders").closest("tr")).toHaveTextContent("Entry orders1208238");

    const tickers = within(screen.getByRole("table", { name: "Each ticker's contribution" })).getAllByRole("row");
    expect(tickers[1]).toHaveTextContent(/^AAPL70\+18,000\+18\.00%55%\+0\.30 R$/);
    expect(within(tickers[1]!).getByRole("link", { name: "AAPL" })).toHaveAttribute(
      "href",
      "/backtest?ticker=AAPL&signal=connors_rsi2_long&eng=vectorized&filter=market&b=SPY",
    );
    expect(screen.getByRole("link", { name: /Each ticker on its own/ })).toHaveAttribute("href", "/watchlist?w=us_large&signal=connors_rsi2_long&filter=market");

    const trades = within(screen.getByRole("table", { name: "Trades" })).getAllByRole("columnheader");
    expect(trades[0]).toHaveTextContent("Ticker");
    expect(screen.getByRole("table", { name: "Trades" })).toHaveTextContent("MSFT");
  });

  it("switches engines and says whether they agree", async () => {
    result = { ...portfolioResult, runs: [makePortfolioRun("vectorized"), makePortfolioRun("cerebro")] };
    renderPage(RESULT_URL.replace("eng=vectorized", "eng=vectorized,cerebro"));
    expect(await screen.findByText("✓ Both engines produced identical results.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "cerebro" }));
    expect(screen.getByText("Each ticker's contribution (cerebro)")).toBeInTheDocument();
    result = portfolioResult;
  });
});

const storedRuns = () => (JSON.parse(localStorage.getItem("tradescan.runs") ?? '{"runs":[]}') as { runs: Record<string, unknown>[] }).runs;

describe("PortfolioPage pinning", () => {
  it("pins the shown run with its universe, portfolio settings and priority, and unpins it", async () => {
    renderPage(RESULT_URL);
    await userEvent.click(await screen.findByRole("button", { name: "Pin run" }));
    expect(storedRuns()).toHaveLength(1);
    expect(storedRuns()[0]).toMatchObject({
      kind: "portfolio",
      name: "us_large connors_rsi2_long",
      universe: "us_large",
      tickers: ["AAPL", "MSFT"],
      missing: ["TSLA"],
      engine: "vectorized",
      portfolio: { max_positions: 5, max_exposure_pct: 100 },
      priority: { name: "momentum", params: { lookback: 252, skip: 21 } },
      stats: { full: { skipped_no_slot: 30 }, in_sample: { orders: 82 }, out_of_sample: { orders: 38 } },
      monteCarlo: null,
      form: { universe: { watchlist: "us_large", tickers: "" }, engines: ["vectorized"], priority: "momentum", settings: { portfolio: { max_positions: 5 } } },
    });
    expect(storedRuns()[0]).not.toHaveProperty("trades");
    expect(screen.getByRole("link", { name: "Compare 1 pinned →" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Unpin run" }));
    expect(storedRuns()).toHaveLength(0);
  });

  it("pins the engine that is shown", async () => {
    result = { ...portfolioResult, runs: [makePortfolioRun("vectorized"), makePortfolioRun("cerebro")] };
    renderPage(RESULT_URL.replace("eng=vectorized", "eng=vectorized,cerebro"));
    await userEvent.click(await screen.findByRole("radio", { name: "cerebro" }));
    await userEvent.click(screen.getByRole("button", { name: "Pin cerebro run" }));
    expect(storedRuns()[0]).toMatchObject({ engine: "cerebro", form: { engines: ["cerebro"] } });
    result = portfolioResult;
  });
});
