import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { config, signals, walkForwardResult } from "../test/fixtures";
import { WalkForwardPage } from "./WalkForwardPage";
import { requestBody, requestUrl } from "../test/fetch";

vi.mock("../components/charts/EquityChart", () => ({ EquityChart: () => null }));

const RESPONSES: Record<string, unknown> = {
  "/config": config,
  "/signals": signals,
  "/walk-forward": walkForwardResult,
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
      { path: "/walk-forward", element: <WalkForwardPage /> },
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

const requestBodies = () =>
  vi
    .mocked(globalThis.fetch)
    .mock.calls.filter(([input]) => requestUrl(input).endsWith("/walk-forward"))
    .map(([, init]) => requestBody(init) as Record<string, unknown>);

const URL =
  "/walk-forward?ticker=SPY&signal=connors_rsi2_long&ax1=signal.oversold&ax1v=5:15:5&ax2=exit.target.target_r&ax2v=2:3:1";

describe("WalkForwardPage", () => {
  it("sets the windows, the scheme and the metric and runs the walk-forward", async () => {
    const router = renderPage("/walk-forward?ticker=SPY&signal=connors_rsi2_long");
    await userEvent.click(await screen.findByRole("button", { name: "Add a parameter" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Parameter 1" }), "signal.oversold");
    expect(
      screen.getByText("9 combinations × 6 in-sample windows = 54 backtests (at most 2000, 200 combinations)"),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/Out-of-sample share/)).not.toBeInTheDocument();

    const windows = screen.getByLabelText(/^Windows/);
    await userEvent.clear(windows);
    await userEvent.type(windows, "8");
    expect(
      screen.getByText("9 combinations × 9 in-sample windows = 81 backtests (at most 2000, 200 combinations)"),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Anchored" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Pick by/ }), "expectancy_r");
    await userEvent.click(screen.getByRole("button", { name: "Run walk-forward" }));

    await waitFor(() => expect(router.state.location.search).toContain("scheme=anchored"));
    expect(router.state.location.search).toContain("wm=expectancy_r");
    await waitFor(() =>
      expect(requestBodies().at(-1)).toMatchObject({
        ticker: "SPY",
        scheme: "anchored",
        metric: "expectancy_r",
        settings: { walk_forward: { windows: 8 } },
        axes: [{ target: "signal", owner: null, name: "oversold", values: [6, 7, 8, 9, 10, 11, 12, 13, 14] }],
      }),
    );
  });

  it("blocks a walk-forward over the backtest cap", async () => {
    renderPage(
      `${URL.replace("ax1v=5:15:5", "ax1v=1:50:1").replace("ax2v=2:3:1", "ax2v=0.25:1:0.25")}&set.walk_forward.windows=12`,
    );
    expect(
      await screen.findByText(
        "200 combinations × 13 in-sample windows = 2600 backtests (at most 2000, 200 combinations)",
      ),
    ).toHaveClass("text-down");
    expect(screen.getByRole("button", { name: "Run walk-forward" })).toBeDisabled();
    expect(requestBodies()).toHaveLength(0);
  });

  it("shows every window, the stitched curve against the unchanged setup and the setting to trade next", async () => {
    renderPage(URL);
    const table = await screen.findByRole("table", { name: "Walk-forward windows" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(4);
    expect(within(rows[1]!).getByText("Oversold level 10, Distance 2")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("2022-06-01 → 2023-10-12")).toHaveClass("text-warn"); // ran past its window
    expect(within(rows[2]!).getByText("2023-10-12 → 2025-02-03")).toHaveClass("text-warn"); // started late
    for (const cell of within(rows[3]!).getAllByText("2025-02-03 → 2026-10-13"))
      expect(cell).not.toHaveClass("text-warn"); // its own bars
    expect(within(rows[3]!).getByText("none qualified, held cash")).toBeInTheDocument();
    expect(within(rows[3]!).getByText("0 of 6")).toBeInTheDocument();

    expect(
      screen.getByText("1 combination could not run and were never picked, e.g. connors_rsi2_long: test failure"),
    ).toBeInTheDocument();
    expect(screen.getByText("Walk-forward efficiency").nextSibling).toHaveTextContent("0.12");
    expect(screen.getByText("unchanged setup +4.5%")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /stitched out-of-sample curve/ })).toBeInTheDocument();

    expect(screen.getByText("Oversold level 10, Distance 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Backtest →" })).toHaveAttribute(
      "href",
      "/backtest?ticker=SPY&signal=connors_rsi2_long&eng=vectorized&ex.target.target_r=3",
    );
    expect(screen.getByText("1 out-of-sample trade")).toBeInTheDocument();
  });
});
