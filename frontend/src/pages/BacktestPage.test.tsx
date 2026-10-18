import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { PinnedRunsProvider } from "../state/pinnedRuns";
import { ThemeProvider } from "../state/theme";
import { appliedRule, backtestResult, config, filterRules, signals } from "../test/fixtures";
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

describe("BacktestPage out-of-sample results", () => {
  it("shows both periods next to the full history and links the setup to a sweep", async () => {
    renderPage("/backtest?ticker=SPY&signal=connors_rsi2_long&sig.connors_rsi2_long.oversold=15&set.backtest.oos_pct=20");
    const periods = await screen.findByRole("table", { name: "Metrics of the full history and of the in-sample and out-of-sample periods" });
    const sharpe = within(periods).getByRole("row", { name: /Sharpe/ });
    expect(within(sharpe).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["0.80", "1.10", "0.20"]);
    expect(screen.getByText("Out-of-sample: only 12 trades, too few to trust the metrics.")).toBeInTheDocument();
    expect(backtestBodies().at(-1)).toMatchObject({ settings: { backtest: { oos_pct: 20 } } });
    expect(screen.getByLabelText("Out-of-sample share (% of history)")).toHaveValue(20);
    expect(screen.getByRole("link", { name: "Sweep parameters of this setup →" })).toHaveAttribute(
      "href",
      "/sweep?ticker=SPY&signal=connors_rsi2_long&set.backtest.oos_pct=20&sig.connors_rsi2_long.oversold=15",
    );
  });

  it("explains a missing split", async () => {
    RESPONSES["/backtest"] = { ...backtestResult, split: null, runs: backtestResult.runs.map((run) => ({ ...run, in_sample: null, out_of_sample: null })) };
    renderPage("/backtest?ticker=SPY&signal=connors_rsi2_long");
    expect(await screen.findByText(/The history is too short to split/)).toBeInTheDocument();
    RESPONSES["/backtest"] = backtestResult;
  });
});

describe("BacktestPage Monte Carlo", () => {
  it("shows the run's order next to each method's spread and sends the Monte Carlo settings", async () => {
    renderPage("/backtest?ticker=SPY&signal=connors_rsi2_long&set.monte_carlo.seed=7&set.monte_carlo.simulations=2000");
    const table = await screen.findByRole("table", { name: "Monte Carlo of the run's trades" });
    const cells = (name: RegExp) => within(within(table).getByRole("row", { name })).getAllByRole("cell").map((cell) => cell.textContent);
    expect(cells(/Final return/)).toEqual(["+9.1%", "+9.1%", "+9.1%", "+9.1%", "-7.3%", "+8.8%", "+26.4%"]);
    expect(cells(/Max drawdown/)).toEqual(["-6.2%", "-14.8%", "-8.4%", "-5.1%", "-21.5%", "-9.7%", "-4.8%"]);
    expect(cells(/losing streak/)).toEqual(["5", "9", "6", "4", "10", "6.5", "4"]);
    expect(cells(/Chance of ruin \(drawdown ≥ 50%\)/)).toEqual(["not reached", "0.0%", "0.4%"]);
    expect(screen.getByText(/42 closed trades resampled 1,000 times per method/)).toBeInTheDocument();

    expect(backtestBodies().at(-1)).toMatchObject({ settings: { monte_carlo: { seed: 7, simulations: 2000 } } });
    expect(screen.getByLabelText("Random seed")).toHaveValue(7);
    expect(screen.getByRole("button", { name: "Run backtest" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "Sweep parameters of this setup →" })).toHaveAttribute("href", "/sweep?ticker=SPY&signal=connors_rsi2_long");
  });

  it("explains a run with too few trades", async () => {
    RESPONSES["/backtest"] = { ...backtestResult, runs: backtestResult.runs.map((run) => ({ ...run, monte_carlo: null })) };
    renderPage("/backtest?ticker=SPY&signal=connors_rsi2_long");
    expect(await screen.findByText(/Too few closed trades for a Monte Carlo/)).toBeInTheDocument();
    RESPONSES["/backtest"] = backtestResult;
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

  it("sends the chosen filters, with a benchmark only once a filter compares one", async () => {
    renderPage("/backtest?ticker=SPY&signal=connors_rsi2_long");
    await screen.findByRole("button", { name: "Pin run" });
    expect(backtestBodies().at(-1)).toMatchObject({ filters: [], benchmark: null });
    expect(screen.getByText("No filters: every signal places its order.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Trend filter", pressed: false }));
    await userEvent.type(screen.getByLabelText("SMA length (bars)"), "100");
    expect(screen.getByText("Close above SMA(100) for longs, below it for shorts")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /^Benchmark/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Market filter", pressed: false }));
    const benchmark = screen.getByRole("textbox", { name: /^Benchmark/ });
    expect(benchmark).toHaveAttribute("placeholder", "SPY");
    await userEvent.type(benchmark, "qqq");
    await userEvent.click(screen.getByRole("button", { name: "Run backtest" }));

    await waitFor(() =>
      expect(backtestBodies().at(-1)).toMatchObject({
        filters: [
          { name: "trend", params: { period: 100 } },
          { name: "market", params: {} },
        ],
        benchmark: "QQQ",
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset 3 changed" }));
    expect(screen.getByRole("button", { name: "Trend filter", pressed: false })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /^Benchmark/ })).not.toBeInTheDocument();
  });

  it("lists the filters and the benchmark a run used", async () => {
    RESPONSES["/backtest"] = { ...backtestResult, filters: [appliedRule(filterRules[1]!)], benchmark: "QQQ" };
    try {
      renderPage("/backtest?ticker=SPY&signal=connors_rsi2_long&filter=market&b=QQQ");
      const line = await screen.findByText(/^Filters: Benchmark close above its SMA\(200\)/);
      expect(line).toHaveTextContent("Filters: Benchmark close above its SMA(200) for longs, below it for shorts · benchmark QQQ");
    } finally {
      RESPONSES["/backtest"] = backtestResult;
    }
  });
});

describe("BacktestPage pyramiding", () => {
  it("sends the pyramiding settings and shows the units of each position", async () => {
    const trade = {
      direction: "long" as const, signal_date: "2024-03-01", entry_date: "2024-03-04", exit_date: "2024-03-15", entry_price: 102,
      exit_price: 110, size: 300, pnl: 2400, r_multiple: 2.4, exit_reason: "trailing",
      adds: [{ date: "2024-03-06", price: 102 }, { date: "2024-03-08", price: 104 }],
    };
    RESPONSES["/backtest"] = {
      ...backtestResult,
      config: { ...backtestResult.config, max_units: 3, add_every_atr: 1 },
      runs: backtestResult.runs.map((run) => ({ ...run, trades: [trade] })),
    };
    try {
      renderPage("/backtest?ticker=SPY&signal=connors_rsi2_long&set.pyramid.max_units=3&set.pyramid.add_every_atr=1");
      expect(await screen.findByText(/pyramiding up to 3 units 1.00 ATR apart/)).toBeInTheDocument();
      expect(backtestBodies().at(-1)).toMatchObject({ settings: { pyramid: { max_units: 3, add_every_atr: 1 } } });
      expect(screen.getByLabelText("Max units")).toHaveValue(3);
      expect(screen.getByLabelText("Add every (ATR)")).toHaveValue(1);

      const table = screen.getByRole("table", { name: "Trades" });
      expect(within(table).getByRole("columnheader", { name: /Units/ })).toBeInTheDocument();
      expect(within(table).getByTitle("added 2024-03-06 at 102.00; added 2024-03-08 at 104.00")).toHaveTextContent("3");
    } finally {
      RESPONSES["/backtest"] = backtestResult;
    }
  });

  it("leaves the units column out while no position was pyramided", async () => {
    RESPONSES["/backtest"] = { ...backtestResult, runs: backtestResult.runs.map((run) => ({ ...run, trades: [{ ...backtestTrade, adds: [] }] })) };
    try {
      renderPage("/backtest?ticker=SPY&signal=connors_rsi2_long");
      const table = await screen.findByRole("table", { name: "Trades" });
      expect(within(table).queryByRole("columnheader", { name: /Units/ })).not.toBeInTheDocument();
      expect(screen.queryByText(/pyramiding up to/)).not.toBeInTheDocument();
    } finally {
      RESPONSES["/backtest"] = backtestResult;
    }
  });
});

const backtestTrade = {
  direction: "long" as const, signal_date: "2024-03-01", entry_date: "2024-03-04", exit_date: "2024-03-08", entry_price: 170,
  exit_price: 178, size: 100, pnl: 780, r_multiple: 1.6, exit_reason: "target",
};
