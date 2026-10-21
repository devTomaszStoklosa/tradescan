import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { downloadFile } from "../lib/csv";
import type { PinnedRun } from "../lib/runs";
import { encodeRuns } from "../lib/runsFile";
import { PinnedRunsProvider } from "../state/pinnedRuns";
import { MemoryRunStore } from "../test/runStore";
import {
  config,
  makeMetrics,
  makeMonteCarlo,
  makePortfolioPin,
  makeRotationPin,
  makeRun,
  makePortfolioRun,
  signals,
} from "../test/fixtures";
import { ComparePage } from "./ComparePage";
import { requestUrl } from "../test/fetch";

vi.mock("../components/charts/EquityChart", () => ({
  EquityChart: ({ series, label }: { series: { label: string }[]; label: string }) => (
    <div role="img" aria-label={label}>
      {series.map((item) => item.label).join(" | ")}
    </div>
  ),
}));

vi.mock("../lib/csv", async (original) => ({
  ...(await original<typeof import("../lib/csv")>()),
  downloadFile: vi.fn(),
}));

/** Where versions before server-side runs kept the pinned runs. */
const BROWSER_KEY = "tradescan.runs";

const base = makeRun(1, {}, { name: "baseline" });
const wideStop = makeRun(
  2,
  { config: { ...base.config, atr_mult: 3 }, metrics: makeMetrics({ total_return_pct: 20, trades: 7 }) },
  { name: "wide stop" },
);
const portfolio = makePortfolioPin(3, {}, { name: "top 5" });

let store = new MemoryRunStore();

function pin(runs: PinnedRun[]) {
  store = new MemoryRunStore(runs);
}

function renderPage() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = requestUrl(input);
    const body = url.endsWith("/config") ? config : url.endsWith("/signals") ? signals : null;
    return new Response(JSON.stringify(body), {
      status: body ? 200 : 404,
      headers: { "Content-Type": "application/json" },
    });
  });
  const router = createMemoryRouter([{ path: "/compare", element: <ComparePage /> }], { initialEntries: ["/compare"] });
  render(
    <PinnedRunsProvider store={store}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </PinnedRunsProvider>,
  );
}

const table = (name: string) => screen.getByRole("table", { name });

/** The parts of `portfolio` that differ for another engine's run. */
const snapshotOf = (engine: string) => {
  const run = makePortfolioRun(engine, {
    equity: [
      { time: "2016-01-04", value: 100000 },
      { time: "2026-10-13", value: 114000 },
    ],
  });
  return { engine, equity: run.equity, form: { ...portfolio.form, engines: [engine] } };
};

describe("ComparePage", () => {
  beforeEach(() => {
    vi.mocked(downloadFile).mockClear();
    store = new MemoryRunStore();
  });

  it("explains how to pin when nothing is pinned", async () => {
    renderPage();
    expect(await screen.findByText("No pinned runs yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
  });

  it("shows only differing parameters, the best metrics and one curve per run", async () => {
    pin([base, wideStop]);
    renderPage();

    const parameters = await screen.findByRole("table", { name: "Parameters of the pinned runs" });
    expect(await within(parameters).findByText("Stop distance")).toBeInTheDocument();
    expect(within(parameters).getAllByRole("row")).toHaveLength(2);
    expect(within(parameters).queryByText("Ticker")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(within(table("Parameters of the pinned runs")).getByText("Ticker")).toBeInTheDocument();

    const totalReturn = within(table("Metrics of the pinned runs")).getByRole("row", { name: /Total return/ });
    expect(within(totalReturn).getAllByRole("cell")[1]).toHaveTextContent("+20.00% (best)");
    expect(screen.getByRole("img", { name: "Return of the pinned runs since their first bar" })).toHaveTextContent(
      "#1 baseline | #2 wide stop",
    );
    expect(
      within(screen.getByRole("article", { name: "Run 2" })).getByText("Only 7 trades: too few to trust the metrics."),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("article", { name: "Run 1" })).getByRole("link", { name: "Open in Backtest" }),
    ).toHaveAttribute(
      "href",
      // The rules are written out, so the run reopens with them even if the server's defaults change.
      "/backtest?ticker=SPY&signal=connors_rsi2_long&eng=vectorized&entry=next_open&exit=target%2Ctime",
    );
  });

  it("checks every run out-of-sample and switches the metrics to one period", async () => {
    const old = makeRun(3, { split: null, config: { ...base.config, oos_pct: undefined } }, { name: "old pin" });
    pin([base, wideStop, old]);
    renderPage();

    const check = await screen.findByRole("table", { name: "Out-of-sample check of the pinned runs" });
    const baseline = within(check).getByRole("row", { name: /baseline/ });
    const few = " (fewer than 20 trades)"; // read out instead of the asterisk
    expect(
      within(baseline)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual([
      "2023-07-03 (30%)",
      "1.10",
      `0.20*${few}`,
      "+0.21 R",
      `+0.21 R*${few}`,
      "1.60",
      `1.60*${few}`,
      "30",
      `12*${few}`,
    ]);
    expect(within(check).getByRole("row", { name: /old pin/ })).toHaveTextContent(
      "No split: pinned before out-of-sample results",
    );

    await userEvent.click(screen.getByRole("radio", { name: "Out-of-sample" }));
    const sharpe = within(table("Metrics of the pinned runs, out-of-sample")).getByRole("row", { name: /Sharpe/ });
    expect(
      within(sharpe)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["0.20", "0.20", "–"]);
    // Runs pinned before out-of-sample results have no share, so the parameter differs.
    expect(within(table("Parameters of the pinned runs")).getByText("Out-of-sample share")).toBeInTheDocument();
  });

  it("compares the Monte Carlo of every run, one method at a time", async () => {
    const few = makeRun(
      2,
      { monteCarlo: makeMonteCarlo({ trades: 12, ruin_drawdown_pct: 30 }) },
      { name: "few trades" },
    );
    const old = makeRun(3, { monteCarlo: null }, { name: "old pin" });
    pin([base, few, old]);
    renderPage();

    await screen.findByRole("table", { name: "Monte Carlo of the pinned runs' trades" });
    const simulations = () => table("Monte Carlo of the pinned runs' trades");
    const cells = (name: RegExp) =>
      within(within(simulations()).getByRole("row", { name }))
        .getAllByRole("cell")
        .map((cell) => cell.textContent);
    expect(screen.getByRole("radio", { name: "Bootstrapped" })).toBeChecked();
    expect(cells(/baseline/)).toEqual(["42", "-7.3%", "+8.8%", "-21.5%", "-9.7%", "10", "6.5", "0.4% at 50%"]);
    expect(cells(/few trades/)[0]).toBe("12* (fewer than 20 trades)");
    expect(cells(/few trades/).at(-1)).toBe("0.4% at 30%");
    expect(within(simulations()).getByRole("row", { name: /old pin/ })).toHaveTextContent(
      "No Monte Carlo: pinned before Monte Carlo results",
    );

    await userEvent.click(screen.getByRole("radio", { name: "Shuffled" }));
    expect(cells(/baseline/)).toEqual(["42", "+9.1%", "+9.1%", "-14.8%", "-8.4%", "9", "6", "0.0% at 50%"]);
    // The ruin level differs between the runs, so it is a parameter that differs.
    expect(within(table("Parameters of the pinned runs")).getByText("Monte Carlo · Ruin level")).toBeInTheDocument();
  });

  it("hides, renames and removes runs and keeps the change on the server", async () => {
    pin([base, wideStop]);
    renderPage();
    const second = await screen.findByRole("article", { name: "Run 2" });

    await userEvent.click(within(second).getByRole("button", { name: "Hide" }));
    expect(screen.getByRole("img", { name: /Return of the pinned runs/ })).toHaveTextContent(/^#1 baseline$/);
    expect(screen.getByText("Show at least two runs to see what differs.")).toBeInTheDocument();
    await waitFor(() => expect(store.runs()[1]?.hidden).toBe(true));

    const name = within(screen.getByRole("article", { name: "Run 1" })).getByRole("textbox", { name: "Name of run 1" });
    await userEvent.clear(name);
    await userEvent.type(name, "RSI2 default{Enter}");
    await waitFor(() => expect(store.runs()[0]?.name).toBe("RSI2 default"));

    await userEvent.click(within(second).getByRole("button", { name: "Remove" }));
    expect(screen.queryByRole("article", { name: "Run 2" })).not.toBeInTheDocument();
    await waitFor(() => expect(store.runs()).toHaveLength(1));
  });

  it("removes all runs only after confirmation", async () => {
    pin([base, wideStop]);
    renderPage();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    await screen.findByRole("article", { name: "Run 2" });

    await userEvent.click(screen.getByRole("button", { name: "Remove all" }));
    expect(screen.getAllByRole("article")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Remove all" }));
    expect(confirm).toHaveBeenCalledWith("Remove all 2 pinned runs? Export them first if you want a backup.");
    expect(screen.getByText("No pinned runs yet")).toBeInTheDocument();
    await waitFor(() => expect(store.records).toEqual([]));
  });

  it("exports the runs and imports them back without duplicates", async () => {
    pin([base]);
    renderPage();
    await screen.findByRole("article", { name: "Run 1" });

    await userEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    const [filename, content, type] = vi.mocked(downloadFile).mock.calls[0] ?? [];
    expect(filename).toMatch(/^tradescan-runs-\d{4}-\d{2}-\d{2}\.json$/);
    expect(type).toBe("application/json");
    expect(JSON.parse(content ?? "")).toEqual(encodeRuns([base]));

    const file = JSON.stringify(encodeRuns([base, wideStop]));
    await userEvent.upload(
      screen.getByLabelText("Runs file to import"),
      new File([file], "runs.json", { type: "application/json" }),
    );
    expect(await screen.findByText("Imported 1 run. 1 run already pinned.")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(store.runs().map((run) => run.name)).toEqual(["baseline", "wide stop"]);
  });

  it("compares a portfolio run with a backtest run, with its stats in the chosen period", async () => {
    pin([base, portfolio]);
    renderPage();

    const card = await screen.findByRole("article", { name: "Run 3" });
    expect(card).toHaveTextContent("us_large");
    expect(card).toHaveTextContent("portfolio of 2 tickers · vectorized · 2016-01-04 → 2026-10-13");
    expect(within(card).getByRole("link", { name: "Open in Portfolio" })).toHaveAttribute(
      "href",
      "/portfolio?w=us_large&signal=connors_rsi2_long&eng=vectorized&entry=next_open&exit=target%2Ctime&filter=market&prio=momentum",
    );

    const parameters = table("Parameters of the pinned runs");
    expect(await within(parameters).findByText("Portfolio · Max positions")).toBeInTheDocument();
    expect(
      within(within(parameters).getByRole("row", { name: /^Run/ }))
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["Backtest", "Portfolio"]);
    expect(within(parameters).getByRole("row", { name: /^Priority/ })).toHaveTextContent("Momentum");

    const orders = () =>
      within(screen.getByRole("table", { name: /^Portfolio stats of the pinned portfolio runs/ })).getByRole("row", {
        name: /Entry orders/,
      });
    const stats = screen.getByRole("table", { name: "Portfolio stats of the pinned portfolio runs" });
    expect(
      within(stats)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Portfolio", "#3top 5"]);
    expect(orders()).toHaveTextContent("Entry orders120");
    await userEvent.click(screen.getByRole("radio", { name: "Out-of-sample" }));
    expect(
      screen.getByRole("table", { name: "Portfolio stats of the pinned portfolio runs, out-of-sample" }),
    ).toBeInTheDocument();
    expect(orders()).toHaveTextContent("Entry orders38");

    expect(
      within(table("Monte Carlo of the pinned runs' trades")).getByRole("row", { name: /top 5/ }),
    ).toHaveTextContent("No Monte Carlo: the portfolio backtest does not simulate its trades.");
  });

  it("compares a rotation run with a backtest run, with its stats in the chosen period", async () => {
    pin([base, makeRotationPin(4, {}, { name: "top 3 etf" })]);
    renderPage();

    const card = await screen.findByRole("article", { name: "Run 4" });
    expect(card).toHaveTextContent("etfmomentum rotation");
    expect(card).toHaveTextContent("Ranking: Return from 252 bars ago to 21 bars ago · weights: Picks weighted by 1 /");
    expect(card).toHaveTextContent("rotation of 2 tickers, top 3 monthly · vectorized · 2017-10-31 → 2026-10-16");
    expect(within(card).getByRole("link", { name: "Open in Rotation" })).toHaveAttribute(
      "href",
      "/rotation?w=etf&rank=momentum&wt=inverse_volatility&safe=TLT&set.rotation.holdings=3",
    );

    const parameters = table("Parameters of the pinned runs");
    expect(await within(parameters).findByText("Rotation · Holdings")).toBeInTheDocument();
    expect(
      within(within(parameters).getByRole("row", { name: /^Run/ }))
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["Backtest", "Rotation"]);
    expect(within(parameters).getByRole("row", { name: /^Weights/ })).toHaveTextContent("Inverse volatility");
    expect(within(parameters).getByRole("row", { name: /^Safe asset/ })).toHaveTextContent("TLT");

    const rebalances = () =>
      within(screen.getByRole("table", { name: /^Rotation stats of the pinned rotation runs/ })).getByRole("row", {
        name: /^Rebalances/,
      });
    const stats = screen.getByRole("table", { name: "Rotation stats of the pinned rotation runs" });
    expect(
      within(stats)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Rotation", "#4top 3 etf"]);
    expect(rebalances()).toHaveTextContent("Rebalances108");
    await userEvent.click(screen.getByRole("radio", { name: "Out-of-sample" }));
    expect(
      screen.getByRole("table", { name: "Rotation stats of the pinned rotation runs, out-of-sample" }),
    ).toBeInTheDocument();
    expect(rebalances()).toHaveTextContent("Rebalances32");
    expect(screen.queryByRole("heading", { name: "Portfolio stats" })).not.toBeInTheDocument();

    expect(
      within(table("Out-of-sample check of the pinned runs")).getByRole("row", { name: /top 3 etf/ }),
    ).toHaveTextContent("2024-02-07 (30%)");
    expect(
      within(table("Monte Carlo of the pinned runs' trades")).getByRole("row", { name: /top 3 etf/ }),
    ).toHaveTextContent("No Monte Carlo: the rotation does not simulate its holdings.");
  });

  it("shows no portfolio stats without a shown portfolio run", async () => {
    pin([base, wideStop, portfolio]);
    renderPage();
    expect(await screen.findByRole("heading", { name: "Portfolio stats" })).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("article", { name: "Run 3" })).getByRole("button", { name: "Hide" }));
    expect(screen.queryByRole("heading", { name: "Portfolio stats" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(within(table("Parameters of the pinned runs")).getByText("Ticker")).toBeInTheDocument();
    expect(within(table("Parameters of the pinned runs")).queryByText("Universe")).not.toBeInTheDocument();
  });

  it("exports and imports portfolio runs next to backtest runs", async () => {
    const cerebro = makePortfolioPin(4, snapshotOf("cerebro"), { name: "top 5 cerebro" });
    pin([base, portfolio, cerebro]);
    renderPage();
    await screen.findByRole("article", { name: "Run 4" });
    await userEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    const content = vi.mocked(downloadFile).mock.calls[0]?.[1] ?? "";
    expect(JSON.parse(content)).toEqual(encodeRuns([base, portfolio, cerebro]));

    vi.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Remove all" }));
    await userEvent.upload(
      screen.getByLabelText("Runs file to import"),
      new File([content], "runs.json", { type: "application/json" }),
    );
    expect(await screen.findByText("Imported 3 runs.")).toBeInTheDocument();
    expect(
      within(screen.getByRole("article", { name: "Run 4" })).getByRole("link", { name: "Open in Portfolio" }),
    ).toBeInTheDocument();
    expect(store.runs().map((run) => run.name)).toEqual(["baseline", "top 5", "top 5 cerebro"]);
  });

  it("reports an invalid import file", async () => {
    renderPage();
    await screen.findByText("No pinned runs yet");
    await userEvent.upload(
      screen.getByLabelText("Runs file to import"),
      new File(["{"], "runs.json", { type: "application/json" }),
    );
    expect(await screen.findByText("Import failed: The file is not valid JSON")).toBeInTheDocument();
  });

  it("reports runs left in this browser that it cannot read, and keeps them", async () => {
    localStorage.setItem(BROWSER_KEY, JSON.stringify({ version: 1, runs: [{ id: 1 }] }));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      'Pinned runs saved in this browser could not be read (Run 1 has an invalid "id").',
    );
    expect(localStorage.getItem(BROWSER_KEY)).not.toBeNull();
  });

  it("moves the runs left in this browser to the server once", async () => {
    pin([base]);
    localStorage.setItem(BROWSER_KEY, JSON.stringify(encodeRuns([base, wideStop])));
    renderPage();
    expect(
      await screen.findByText("Moved 1 pinned run from this browser to the server. 1 run already there."),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(store.runs().map((run) => run.name)).toEqual(["baseline", "wide stop"]);
    expect(localStorage.getItem(BROWSER_KEY)).toBeNull();
  });

  it("keeps the runs that did not fit on the server in this browser", async () => {
    const runs = Array.from({ length: 8 }, (_, index) =>
      makeRun(index + 1, { config: { ...base.config, atr_mult: index + 1 } }, { name: `run ${index + 1}` }),
    );
    pin(runs.slice(0, 7));
    const another = makeRun(2, { config: { ...base.config, atr_mult: 10 } });
    localStorage.setItem(BROWSER_KEY, JSON.stringify(encodeRuns([runs[7]!, another])));
    renderPage();
    expect(
      await screen.findByText(
        "Moved 1 pinned run from this browser to the server. 1 run did not fit (the limit is 8): remove some runs and reload the page to move the rest.",
      ),
    ).toBeInTheDocument();
    expect(store.records).toHaveLength(8);
    expect(localStorage.getItem(BROWSER_KEY)).not.toBeNull();
  });

  it("shows why a change was not saved and what the server has", async () => {
    pin([base, wideStop]);
    renderPage();
    const second = await screen.findByRole("article", { name: "Run 2" });
    vi.spyOn(store, "remove").mockRejectedValueOnce(new Error("Cannot reach the tradescan server"));
    await userEvent.click(within(second).getByRole("button", { name: "Remove" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The change was not saved (Cannot reach the tradescan server).",
    );
    expect(await screen.findByRole("article", { name: "Run 2" })).toBeInTheDocument();
  });

  it("reports runs the server cannot give", async () => {
    vi.spyOn(store, "load").mockRejectedValue(new Error("Cannot reach the tradescan server"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Pinned runs could not be read from the server (Cannot reach the tradescan server).",
    );
    expect(screen.getByText("No pinned runs yet")).toBeInTheDocument();
  });
});
