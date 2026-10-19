import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { config, signals, sweepResult } from "../test/fixtures";
import { SweepPage } from "./SweepPage";

const RESPONSES: Record<string, unknown> = { "/config": config, "/signals": signals, "/sweep": sweepResult };

function renderPage(path: string) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = Object.entries(RESPONSES).find(([route]) => url.endsWith(route))?.[1] ?? null;
    return new Response(JSON.stringify(body), {
      status: body ? 200 : 404,
      headers: { "Content-Type": "application/json" },
    });
  });
  const router = createMemoryRouter(
    [
      { path: "/sweep", element: <SweepPage /> },
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

const sweepBodies = () =>
  vi
    .mocked(globalThis.fetch)
    .mock.calls.filter(([input]) => String(input).endsWith("/sweep"))
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>);

const SWEEP_URL =
  "/sweep?ticker=SPY&signal=connors_rsi2_long&ax1=signal.oversold&ax1v=5:15:5&ax2=exit.target.target_r&ax2v=2:3:1";

describe("SweepPage", () => {
  it("adds a parameter with a range around the setup's value and runs the sweep", async () => {
    localStorage.setItem("tradescan.account", JSON.stringify({ equity: 50000, riskPct: null, lotSize: null }));
    const router = renderPage("/sweep?ticker=SPY&signal=connors_rsi2_long");
    await userEvent.click(await screen.findByRole("button", { name: "Add a parameter" }));
    expect(screen.getByRole("combobox", { name: "Parameter 1" })).toHaveValue("signal.rsi_period");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Parameter 1" }), "signal.oversold");
    expect(screen.getByLabelText("Parameter 1: from")).toHaveValue(6);
    expect(screen.getByLabelText("Parameter 1: to")).toHaveValue(14);
    expect(screen.getByText("9 values: 6, 7, 8, 9, 10, 11, … (setup: 10)")).toBeInTheDocument();
    expect(screen.getByText("9 combinations (at most 200)")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Add a second parameter" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Parameter 2" }), "exit.time.max_hold_bars");
    expect(screen.getByText("9 × 9 = 81 combinations (at most 200)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Run sweep" }));

    await waitFor(() => expect(router.state.location.search).toContain("ax2=exit.time.max_hold_bars"));
    await waitFor(() =>
      expect(sweepBodies().at(-1)).toMatchObject({
        ticker: "SPY",
        settings: { account: { equity: 50000 } },
        axes: [
          { target: "signal", owner: null, name: "oversold", values: [6, 7, 8, 9, 10, 11, 12, 13, 14] },
          { target: "exit", owner: "time", name: "max_hold_bars", values: [16, 17, 18, 19, 20, 21, 22, 23, 24] },
        ],
      }),
    );
    localStorage.clear();
  });

  it("blocks a sweep over the combination cap", async () => {
    renderPage(
      "/sweep?ticker=SPY&signal=connors_rsi2_long&ax1=signal.oversold&ax1v=1:30:1&ax2=exit.time.max_hold_bars&ax2v=1:10:1",
    );
    expect(await screen.findByText("30 × 10 = 300 combinations (at most 200)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run sweep" })).toBeDisabled();
    expect(sweepBodies()).toHaveLength(0);
  });

  it("shows both periods on one scale and the best in-sample cell's details", async () => {
    renderPage(SWEEP_URL);
    const inSample = await screen.findByRole("table", { name: /^In-sample 2016-01-04/ });
    const outOfSample = screen.getByRole("table", { name: /^Out-of-sample \(last 30%\)/ });
    expect(within(inSample).getAllByRole("button")).toHaveLength(6);

    const best = within(inSample).getByRole("button", {
      name: /Oversold level 10, Distance 3: Sharpe 1.40, 30 trades, best in-sample/,
    });
    expect(best).toHaveAttribute("aria-pressed", "true");
    expect(
      within(outOfSample).getByRole("button", {
        name: /Oversold level 10, Distance 3: Sharpe 0.30, 8 trades \(too few to trust\)/,
      }),
    ).toHaveAttribute("data-few");
    expect(
      within(inSample).getByRole("button", { name: /Oversold level 10, Distance 2: .*current setting/ }),
    ).toBeInTheDocument();
    expect(
      within(inSample).getByRole("button", {
        name: /Oversold level 15, Distance 3: could not run \(connors_rsi2_long: test failure\)/,
      }),
    ).toHaveTextContent("×");
    expect(screen.getByText("1 combination could not run, e.g. connors_rsi2_long: test failure")).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: "Oversold level 10, Distance 3" })).toBeInTheDocument();
    expect(screen.getByText("Out-of-sample: only 8 trades, too few to trust the metrics.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Backtest →" })).toHaveAttribute(
      "href",
      "/backtest?ticker=SPY&signal=connors_rsi2_long&eng=vectorized&ex.target.target_r=3",
    );

    await userEvent.click(within(outOfSample).getByRole("button", { name: /Oversold level 5, Distance 2/ }));
    expect(screen.getByRole("heading", { name: "Oversold level 5, Distance 2" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Backtest →" })).toHaveAttribute(
      "href",
      "/backtest?ticker=SPY&signal=connors_rsi2_long&eng=vectorized&sig.connors_rsi2_long.oversold=5",
    );
  });

  it("recolours by another metric without running again", async () => {
    const router = renderPage(SWEEP_URL);
    await screen.findByRole("table", { name: /^In-sample/ });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Colour by" }), "trades");
    expect(router.state.location.search).toContain("m=trades");
    expect(
      within(screen.getByRole("table", { name: /^Out-of-sample/ })).getByRole("button", {
        name: /Oversold level 10, Distance 3: Trades 8/,
      }),
    ).toBeInTheDocument();
    expect(sweepBodies()).toHaveLength(1);
  });
});
