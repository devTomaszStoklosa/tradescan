import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { PinnedRunsProvider } from "../state/pinnedRuns";
import { config, rotationResult, rotationRun, watchlists } from "../test/fixtures";
import { MemoryRunStore } from "../test/runStore";
import { RotationPage } from "./RotationPage";
import { requestBody, requestUrl } from "../test/fetch";

vi.mock("../components/charts/EquityChart", () => ({ EquityChart: () => null }));

let store = new MemoryRunStore();

function renderPage(path: string, result: unknown = rotationResult) {
  store = new MemoryRunStore();
  const responses: Record<string, unknown> = {
    "/config": config,
    "/watchlists": watchlists,
    "/rotation-backtest": result,
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = requestUrl(input);
    const body = Object.entries(responses).find(([route]) => url.endsWith(route))?.[1] ?? null;
    return new Response(JSON.stringify(body), {
      status: body ? 200 : 404,
      headers: { "Content-Type": "application/json" },
    });
  });
  const router = createMemoryRouter([{ path: "/rotation", element: <RotationPage /> }], { initialEntries: [path] });
  render(
    <AccountProvider>
      <PinnedRunsProvider store={store}>
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
    .mock.calls.filter(([input]) => requestUrl(input).endsWith("/rotation-backtest"))
    .map(([, init]) => requestBody(init) as Record<string, unknown>);

describe("RotationPage", () => {
  it("runs the default watchlist with the chosen ranking, weights, rebalance, holdings and safe asset", async () => {
    const router = renderPage("/rotation");
    await screen.findByRole("button", { name: "Run rotation" });
    expect(screen.getByRole("combobox", { name: "Universe" })).toHaveValue("us_large");
    expect(screen.getByRole("combobox", { name: "Ranking (strongest first)" })).toHaveValue("momentum");
    expect(
      within(screen.getByRole("combobox", { name: "Ranking (strongest first)" })).queryByRole("option", {
        name: "Scan score",
      }),
    ).toBeNull();
    expect(screen.getByRole("radio", { name: "Monthly" })).toBeChecked();
    expect(bodies()).toHaveLength(0); // nothing runs before a universe is in the URL

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Weights" }), "inverse_volatility");
    await userEvent.type(screen.getByLabelText("Volatility lookback (bars)"), "20");
    await userEvent.click(screen.getByRole("radio", { name: "Weekly" }));
    await userEvent.type(screen.getByLabelText("Holdings"), "3");
    await userEvent.type(screen.getByPlaceholderText("cash, e.g. TLT"), "tlt");
    expect(screen.getByRole("button", { name: "Reset 5 changed" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Run rotation" }));

    await waitFor(() =>
      expect(router.state.location.search).toBe(
        "?w=us_large&wt=inverse_volatility&reb=weekly&safe=TLT&set.rotation.holdings=3&wp.inverse_volatility.lookback=20",
      ),
    );
    await waitFor(() =>
      expect(bodies().at(-1)).toMatchObject({
        watchlist: "us_large",
        engines: ["vectorized"],
        ranking: { name: "momentum", params: {} },
        weighting: { name: "inverse_volatility", params: { lookback: 20 } },
        rebalance: "weekly",
        safe_asset: "TLT",
        settings: { rotation: { holdings: 3 } },
      }),
    );
  });

  it("does not run with an invalid value", async () => {
    renderPage("/rotation?w=etf");
    await screen.findByRole("button", { name: "Run rotation" });
    await userEvent.type(screen.getByLabelText("Holdings"), "0");
    expect(screen.getByRole("button", { name: "Run rotation" })).toBeDisabled();
  });

  it("shows the run's metrics, stats, picks, contributions and holdings", async () => {
    renderPage("/rotation?w=etf&wt=inverse_volatility&safe=TLT&set.rotation.holdings=3");
    expect(await screen.findByText("No data for: VNQ")).toBeInTheDocument();
    expect(screen.getByText("top 3, rebalanced monthly")).toBeInTheDocument();
    expect(screen.getByText(/a pick at or below 0 over 252 bars goes to TLT/)).toBeInTheDocument();
    expect(screen.getByText("SPY buy & hold +240.7%")).toBeInTheDocument();
    expect(screen.getByText("14%")).toBeInTheDocument(); // defensive: 6.1% in TLT and 7.5% in cash
    expect(screen.getByText("415% / year")).toBeInTheDocument();

    const metrics = screen.getByRole("table", { name: "Rotation metrics by period" });
    expect(
      within(metrics)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Metric", "Full run", "In-sample", "Out-of-sample"]);
    const stats = screen.getByRole("table", { name: "Rotation stats by period" });
    expect(within(stats).getByText("Rebalances").closest("tr")).toHaveTextContent("Rebalances1087632");

    expect(screen.getByText("A rebalance at the 2026-10-16 close would pick")).toBeInTheDocument();
    const picks = within(screen.getByRole("table", { name: "Picks by rank" })).getAllByRole("row");
    expect(picks[1]).toHaveTextContent(/^XLE0\.530\+62\.6%35\.9%yes$/);
    expect(picks[2]).toHaveTextContent("no, its slot goes to TLT");
    expect(screen.getByText(/34\.2% in TLT, 29\.9% in cash/)).toBeInTheDocument();

    const tickers = within(screen.getByRole("table", { name: "Each ticker's contribution" })).getAllByRole("row");
    expect(tickers[1]).toHaveTextContent(/^GLD5\+56,052\+56\.05%80%$/);
    expect(screen.getByText("2 holdings (vectorized)")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Trades" })).toHaveTextContent("rebalance");
    expect(screen.queryByRole("radiogroup", { name: "Engine" })).toBeNull(); // one engine, nothing to switch
  });

  it("runs both engines and switches between their runs", async () => {
    const cerebro = {
      ...rotationRun,
      engine: "cerebro",
      tickers: [rotationRun.tickers[1]!],
      trades: [rotationRun.trades[0]!],
    };
    const router = renderPage("/rotation?w=etf", { ...rotationResult, runs: [rotationRun, cerebro] });
    await screen.findByRole("button", { name: "Run rotation" });
    await userEvent.click(screen.getByRole("button", { name: "cerebro" }));
    expect(screen.queryByText(/Cerebro checks the vectorized engine/)).toBeNull(); // a small universe
    await userEvent.click(screen.getByRole("button", { name: "Run rotation" }));
    await waitFor(() => expect(router.state.location.search).toBe("?w=etf&eng=vectorized%2Ccerebro"));
    await waitFor(() => expect(bodies().at(-1)).toMatchObject({ engines: ["vectorized", "cerebro"] }));

    expect(await screen.findByText("✓ Both engines produced identical results.")).toBeInTheDocument();
    expect(screen.getByText("2 holdings (vectorized)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "cerebro" }));
    expect(screen.getByText("1 holdings (cerebro)")).toBeInTheDocument();
    const tickers = within(screen.getByRole("table", { name: "Each ticker's contribution" })).getAllByRole("row");
    expect(tickers[1]).toHaveTextContent(/^TLT/);
  });

  it("warns that Cerebro is slow on a large universe and needs an engine", async () => {
    const tickers = Array.from({ length: 21 }, (_, index) => `T${index}`).join(",");
    renderPage(`/rotation?t=${tickers}&eng=cerebro`);
    await screen.findByRole("button", { name: "Run rotation" });
    expect(screen.getByText(/Cerebro checks the vectorized engine and is slow/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "cerebro" }));
    expect(screen.queryByText(/Cerebro checks the vectorized engine and is slow/)).toBeNull();
    expect(screen.getByRole("button", { name: "Run rotation" })).toBeDisabled();
  });
});

const storedRuns = () => store.runs();

const RESULT_URL = "/rotation?w=etf&wt=inverse_volatility&safe=TLT&set.rotation.holdings=3";

describe("RotationPage pinning", () => {
  it("pins the shown run with its universe, rotation settings, rules and stats, and unpins it", async () => {
    renderPage(RESULT_URL);
    const pin = await screen.findByRole("button", { name: "Pin run" });
    await waitFor(() => expect(pin).toBeEnabled());
    await userEvent.click(pin);
    await waitFor(() => expect(storedRuns()).toHaveLength(1));
    expect(storedRuns()[0]).toMatchObject({
      kind: "rotation",
      name: "etf momentum rotation",
      universe: "etf",
      tickers: ["GLD", "TLT"],
      missing: ["VNQ"],
      engine: "vectorized",
      rotation: { holdings: 3, absolute_lookback: 252, rebalance: "monthly", safe_asset: "TLT" },
      ranking: { name: "momentum", params: { lookback: 252, skip: 21 } },
      weighting: { name: "inverse_volatility", params: { lookback: 63 } },
      buyHoldBenchmark: "SPY",
      stats: { full: { rebalances: 108 }, in_sample: { rebalances: 76 }, out_of_sample: { rebalances: 32 } },
      split: { out_of_sample_start: "2024-02-07", in_sample: { sharpe: 0.43 }, out_of_sample: { sharpe: 1.09 } },
      form: {
        universe: { watchlist: "etf", tickers: "" },
        engines: ["vectorized"],
        weighting: "inverse_volatility",
        safeAsset: "TLT",
        settings: { rotation: { holdings: 3 } },
      },
    });
    for (const field of ["trades", "holdings", "targets", "signal", "monteCarlo"])
      expect(store.records[0]?.snapshot).not.toHaveProperty(field);
    expect(screen.getByRole("link", { name: "Compare 1 pinned →" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Unpin run" }));
    await waitFor(() => expect(storedRuns()).toHaveLength(0));
  });

  it("pins the engine that is shown", async () => {
    const cerebro = { ...rotationRun, engine: "cerebro" };
    renderPage(`${RESULT_URL}&eng=vectorized,cerebro`, { ...rotationResult, runs: [rotationRun, cerebro] });
    await userEvent.click(await screen.findByRole("radio", { name: "cerebro" }));
    await userEvent.click(screen.getByRole("button", { name: "Pin cerebro run" }));
    await waitFor(() => expect(storedRuns()).toHaveLength(1));
    expect(storedRuns()[0]).toMatchObject({ engine: "cerebro", form: { engines: ["cerebro"] } });
  });
});
