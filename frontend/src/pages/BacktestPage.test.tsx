import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { PinnedRunsProvider } from "../state/pinnedRuns";
import { ThemeProvider } from "../state/theme";
import { backtestResult, config, signals } from "../test/fixtures";
import { BacktestPage } from "./BacktestPage";

vi.mock("../components/charts/EquityChart", () => ({ EquityChart: () => null }));
vi.mock("../components/charts/PriceChart", () => ({ PriceChart: () => null }));

const RESPONSES: Record<string, unknown> = {
  "/config": config,
  "/signals": signals,
  "/backtest": backtestResult,
  "/chart": { ticker: "SPY", candles: [], sma_fast: [], sma_slow: [], events: [] },
};

function renderPage(path: string) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = Object.entries(RESPONSES).find(([route]) => url.endsWith(route))?.[1] ?? null;
    return new Response(JSON.stringify(body), { status: body ? 200 : 404, headers: { "Content-Type": "application/json" } });
  });
  const router = createMemoryRouter([{ path: "/backtest", element: <BacktestPage /> }], { initialEntries: [path] });
  render(
    <ThemeProvider>
      <AccountProvider>
        <PinnedRunsProvider>
          <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
            <RouterProvider router={router} />
          </QueryClientProvider>
        </PinnedRunsProvider>
      </AccountProvider>
    </ThemeProvider>,
  );
}

/** Bodies of the backtest requests sent so far. */
const backtestBodies = () =>
  vi
    .mocked(globalThis.fetch)
    .mock.calls.filter(([input]) => String(input).endsWith("/backtest"))
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>);

const storedRuns = () => (JSON.parse(localStorage.getItem("tradescan.runs") ?? '{"runs":[]}') as { runs: { form: unknown; engine: string }[] }).runs;

describe("BacktestPage pinning", () => {
  it("pins the shown run once and unpins it", async () => {
    renderPage("/backtest?ticker=SPY&signal=connors_rsi2_long&sig.connors_rsi2_long.oversold=15");

    await userEvent.click(await screen.findByRole("button", { name: "Pin run" }));
    expect(storedRuns()).toHaveLength(1);
    expect(storedRuns()[0]).toMatchObject({
      engine: "vectorized",
      form: { ticker: "SPY", signal: "connors_rsi2_long", engines: ["vectorized"], signalParams: { oversold: 15 } },
    });
    expect(screen.getByRole("link", { name: "Compare 1 pinned →" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Unpin run" }));
    expect(storedRuns()).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Pin run" })).toBeInTheDocument();
  });
});

describe("BacktestPage trade rules", () => {
  it("sends the chosen entry and exits", async () => {
    renderPage("/backtest?ticker=SPY&signal=connors_rsi2_long");
    await screen.findByRole("button", { name: "Pin run" });
    expect(backtestBodies().at(-1)).toMatchObject({ entry: { name: "next_open" }, exits: [{ name: "target" }, { name: "time" }] });

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Entry" }), "limit");
    expect(screen.getByText(/^Buy-limit 0.5 ATR below/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Offset (ATR)"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Profit target", pressed: true }));
    await userEvent.type(screen.getByLabelText("Hold for (bars)"), "5");
    expect(screen.getByText("Exit at the open 5 bars after the entry bar")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Run backtest" }));

    await waitFor(() =>
      expect(backtestBodies().at(-1)).toMatchObject({
        entry: { name: "limit", params: { offset_atr: 1 } },
        exits: [{ name: "time", params: { max_hold_bars: 5 } }],
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset 4 changed" }));
    expect(screen.getByRole("combobox", { name: "Entry" })).toHaveValue("next_open");
    expect(screen.getByRole("button", { name: "Profit target", pressed: true })).toBeInTheDocument();
  });
});
