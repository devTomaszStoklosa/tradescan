import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { config, rotationSweepResult, watchlists } from "../test/fixtures";
import { RotationSweepPage } from "./RotationSweepPage";
import { requestBody, requestUrl } from "../test/fetch";

const RESPONSES: Record<string, unknown> = {
  "/config": config,
  "/watchlists": watchlists,
  "/rotation-sweep": rotationSweepResult,
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
      { path: "/rotation-sweep", element: <RotationSweepPage /> },
      { path: "/rotation", element: <p>rotation page</p> },
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
    .mock.calls.filter(([input]) => requestUrl(input).endsWith("/rotation-sweep"))
    .map(([, init]) => requestBody(init) as Record<string, unknown>);

const SWEEP_URL =
  "/rotation-sweep?w=us_large&wt=inverse_volatility&safe=TLT&set.rotation.holdings=3" +
  "&ax1=settings.rotation.holdings&ax1v=2:4:1&ax2=ranking.lookback&ax2v=126:252:126";

describe("RotationSweepPage", () => {
  it("adds a parameter with a range around the rotation's value and runs the sweep", async () => {
    localStorage.setItem("tradescan.account", JSON.stringify({ equity: 50000, riskPct: null, lotSize: null }));
    const router = renderPage("/rotation-sweep");
    await userEvent.click(await screen.findByRole("button", { name: "Add a parameter" }));
    expect(screen.getByRole("combobox", { name: "Universe" })).toHaveValue("us_large");
    expect(screen.getByRole("combobox", { name: "Parameter 1" })).toHaveValue("ranking.lookback");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Parameter 1" }), "settings.rotation.holdings");
    expect(screen.getByText("9 values: 1, 2, 3, 4, 5, 6, … (setup: 5)")).toBeInTheDocument();
    expect(screen.getByText("9 combinations (at most 200)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cerebro/ })).toBeNull(); // sweeps run on the vectorized engine
    await userEvent.click(screen.getByRole("button", { name: "Run sweep" }));

    await waitFor(() => expect(router.state.location.search).toContain("ax1=settings.rotation.holdings"));
    await waitFor(() =>
      expect(sweepBodies().at(-1)).toMatchObject({
        watchlist: "us_large",
        settings: { account: { equity: 50000 } },
        axes: [{ target: "settings", owner: "rotation", name: "holdings", values: [1, 2, 3, 4, 5, 6, 7, 8, 9] }],
      }),
    );
    expect(sweepBodies().at(-1)).not.toHaveProperty("engines");
    localStorage.clear();
  });

  it("blocks a sweep over the combination cap", async () => {
    renderPage("/rotation-sweep?w=us_large&ax1=ranking.lookback&ax1v=2:31:1&ax2=ranking.skip&ax2v=0:9:1");
    expect(await screen.findByText("30 × 10 = 300 combinations (at most 200)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run sweep" })).toBeDisabled();
    expect(sweepBodies()).toHaveLength(0);
  });

  it("shows both periods, the best in-sample cell's metrics and rotation stats, and opens it on the Rotation page", async () => {
    renderPage(SWEEP_URL);
    const inSample = await screen.findByRole("table", { name: /^In-sample 2017-10-31/ });
    const outOfSample = screen.getByRole("table", { name: /^Out-of-sample \(last 30%\)/ });
    expect(within(inSample).getAllByRole("button")).toHaveLength(6);
    expect(screen.getByText("No data for: VNQ")).toBeInTheDocument();
    expect(screen.getByText("6 combinations on the vectorized engine", { exact: false })).toBeInTheDocument();

    const best = within(inSample).getByRole("button", {
      name: /Holdings 4, Lookback 126: Sharpe 0.90, 64 trades, best in-sample/,
    });
    expect(best).toHaveAttribute("aria-pressed", "true");
    expect(
      within(outOfSample).getByRole("button", { name: /Holdings 4, Lookback 126: Sharpe 0.40, 12 trades \(too few/ }),
    ).toHaveAttribute("data-few");
    expect(
      within(inSample).getByRole("button", { name: /Holdings 3, Lookback 252: .*current setting/ }),
    ).toBeInTheDocument();
    expect(
      within(inSample).getByRole("button", {
        name: /Holdings 4, Lookback 252: could not run \(No in-sample rebalance/,
      }),
    ).toHaveTextContent("×");

    expect(screen.getByRole("heading", { name: "Holdings 4, Lookback 126" })).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Rotation stats of the selected combination in both periods" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Out-of-sample: only 12 trades, too few to trust the metrics.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Rotation →" })).toHaveAttribute(
      "href",
      "/rotation?w=us_large&wt=inverse_volatility&safe=TLT&set.rotation.holdings=4&rk.momentum.lookback=126",
    );

    await userEvent.click(within(outOfSample).getByRole("button", { name: /Holdings 3, Lookback 252/ }));
    expect(screen.getByRole("link", { name: "Open in Rotation →" })).toHaveAttribute(
      "href",
      "/rotation?w=us_large&wt=inverse_volatility&safe=TLT&set.rotation.holdings=3",
    );
  });
});
