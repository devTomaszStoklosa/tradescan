import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountProvider } from "../state/account";
import { ThemeProvider } from "../state/theme";
import { config, scanResult, watchlists } from "../test/fixtures";
import { ScanPage } from "./ScanPage";

function mockServer() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.endsWith("/config") ? config : url.endsWith("/watchlists") ? watchlists : url.endsWith("/scan") ? scanResult : null;
    return new Response(JSON.stringify(body), { status: body ? 200 : 404, headers: { "Content-Type": "application/json" } });
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

describe("ScanPage", () => {
  it("runs a scan from the form and shows regime and results", async () => {
    const fetch = mockServer();
    const router = renderPage();

    const scanButton = await screen.findByRole("button", { name: "Scan" });
    expect(screen.getByRole("combobox")).toHaveValue("us_large");
    await userEvent.click(screen.getByRole("radio", { name: "Long" }));
    await userEvent.click(scanButton);

    expect(await screen.findByText("risk-on")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(router.state.location.search).toBe("?w=us_large&dir=long");

    const scanCall = fetch.mock.calls.find(([url]) => String(url).endsWith("/scan"));
    expect(JSON.parse(String(scanCall?.[1]?.body))).toMatchObject({ watchlist: "us_large", direction: "long", account: { equity: null } });
  });

  it("sends the saved account settings with the scan", async () => {
    localStorage.setItem("tradescan.account", JSON.stringify({ equity: 50000, riskPct: 0.5, lotSize: null }));
    const fetch = mockServer();
    renderPage("/?t=AAPL,MSFT");

    expect(await screen.findByText("MSFT")).toBeInTheDocument();
    const scanCall = fetch.mock.calls.find(([url]) => String(url).endsWith("/scan"));
    expect(JSON.parse(String(scanCall?.[1]?.body))).toMatchObject({
      tickers: ["AAPL", "MSFT"],
      account: { equity: 50000, risk_pct: 0.5, lot_size: null },
    });
  });
});
