import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { ThemeProvider } from "../state/theme";
import { config, scanResult, signals, watchlists } from "../test/fixtures";
import { ScanPage } from "./ScanPage";
import { requestBody, requestUrl } from "../test/fetch";

const RESPONSES: Record<string, unknown> = {
  "/config": config,
  "/signals": signals,
  "/watchlists": watchlists,
  "/scan": scanResult,
};

function mockServer() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = requestUrl(input);
    const body = Object.entries(RESPONSES).find(([path]) => url.endsWith(path))?.[1] ?? null;
    return new Response(JSON.stringify(body), {
      status: body ? 200 : 404,
      headers: { "Content-Type": "application/json" },
    });
  });
}

function renderPage(path = "/") {
  const router = createMemoryRouter([{ path: "/", element: <ScanPage /> }], { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <ThemeProvider>
      <AccountProvider>
        <QueryClientProvider client={client}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </AccountProvider>
    </ThemeProvider>,
  );
  return router;
}

const scanRequest = (fetch: ReturnType<typeof mockServer>) => {
  const calls = fetch.mock.calls.filter(([url]) => requestUrl(url).endsWith("/scan"));
  return requestBody(calls.at(-1)?.[1]);
};

describe("ScanPage", () => {
  it("runs a scan from the form and shows regime and results", async () => {
    const fetch = mockServer();
    const router = renderPage();

    const scanButton = await screen.findByRole("button", { name: "Scan" });
    expect(screen.getByRole("combobox", { name: /^Universe/ })).toHaveValue("us_large");
    await userEvent.click(screen.getByRole("radio", { name: "Long" }));
    await userEvent.click(scanButton);

    expect(await screen.findByText("risk-on")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(router.state.location.search).toBe("?w=us_large&dir=long");
    expect(scanRequest(fetch)).toEqual({
      watchlist: "us_large",
      families: [],
      direction: "long",
      period: null,
      benchmark: null,
      settings: {},
      signal_params: {},
    });
  });

  it("sends the saved account settings with the scan", async () => {
    localStorage.setItem("tradescan.account", JSON.stringify({ equity: 50000, riskPct: 0.5, lotSize: null }));
    const fetch = mockServer();
    renderPage("/?t=AAPL,MSFT");

    expect(await screen.findByText("MSFT")).toBeInTheDocument();
    expect(scanRequest(fetch)).toMatchObject({
      tickers: ["AAPL", "MSFT"],
      settings: { account: { equity: 50000, risk_pct: 0.5 } },
    });
  });

  it("puts changed parameters in the URL and the request", async () => {
    const fetch = mockServer();
    const router = renderPage("/?w=us_large");
    await screen.findByText("AAPL");

    await userEvent.type(screen.getByLabelText("Fresh within (bars)"), "5");
    await userEvent.click(screen.getByText("Advanced settings"));
    await userEvent.type(screen.getByLabelText("Stop distance (ATR)"), "3");
    await userEvent.click(screen.getByText("connors_rsi2_long"));
    await userEvent.type(screen.getByLabelText("Oversold level"), "15");
    expect(screen.getByText("RSI(2) < 15 while price is above SMA(200): dip in an uptrend")).toBeInTheDocument();
    expect(screen.getByText("3 changed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Scan" }));

    await vi.waitFor(() =>
      expect(router.state.location.search).toBe(
        "?w=us_large&set.scan.fresh_bars=5&set.risk.atr_mult=3&sig.connors_rsi2_long.oversold=15",
      ),
    );
    await vi.waitFor(() =>
      expect(scanRequest(fetch)).toMatchObject({
        settings: { scan: { fresh_bars: 5 }, risk: { atr_mult: 3 } },
        signal_params: { connors_rsi2_long: { oversold: 15 } },
      }),
    );
  });

  it("links a fired signal to a backtest with the scan's stop and the default trade rules", async () => {
    mockServer();
    renderPage("/?w=us_large&set.risk.atr_mult=3");
    await userEvent.click(await screen.findByText("AAPL"));

    expect(await screen.findByTitle("Backtest donchian_breakout on AAPL")).toHaveAttribute(
      "href",
      "/backtest?ticker=AAPL&signal=donchian_breakout&eng=vectorized&set.risk.atr_mult=3",
    );
  });

  it("blocks a scan with an out-of-range value", async () => {
    mockServer();
    renderPage("/?w=us_large");
    await screen.findByText("AAPL");
    await userEvent.type(screen.getByLabelText("Fresh within (bars)"), "99");
    expect(screen.getByText("Allowed: 1–60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Scan" })).toBeDisabled();
  });
});
