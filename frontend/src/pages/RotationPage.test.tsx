import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { config, rotationResult, watchlists } from "../test/fixtures";
import { RotationPage } from "./RotationPage";

vi.mock("../components/charts/EquityChart", () => ({ EquityChart: () => null }));

function renderPage(path: string) {
  const responses: Record<string, unknown> = {
    "/config": config,
    "/watchlists": watchlists,
    "/rotation-backtest": rotationResult,
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = Object.entries(responses).find(([route]) => url.endsWith(route))?.[1] ?? null;
    return new Response(JSON.stringify(body), {
      status: body ? 200 : 404,
      headers: { "Content-Type": "application/json" },
    });
  });
  const router = createMemoryRouter([{ path: "/rotation", element: <RotationPage /> }], { initialEntries: [path] });
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
    .mock.calls.filter(([input]) => String(input).endsWith("/rotation-backtest"))
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>);

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
    expect(screen.getByText("2 holdings")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Trades" })).toHaveTextContent("rebalance");
  });
});
