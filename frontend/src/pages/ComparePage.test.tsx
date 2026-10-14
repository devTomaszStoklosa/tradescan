import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { downloadFile } from "../lib/csv";
import type { PinnedRun } from "../lib/runs";
import { encodeRuns } from "../lib/runsFile";
import { PinnedRunsProvider } from "../state/pinnedRuns";
import { config, makeMetrics, makeRun, signals } from "../test/fixtures";
import { ComparePage } from "./ComparePage";

vi.mock("../components/charts/EquityChart", () => ({
  EquityChart: ({ series, label }: { series: { label: string }[]; label: string }) => (
    <div role="img" aria-label={label}>
      {series.map((item) => item.label).join(" | ")}
    </div>
  ),
}));

vi.mock("../lib/csv", async (original) => ({ ...(await original<typeof import("../lib/csv")>()), downloadFile: vi.fn() }));

const STORAGE_KEY = "tradescan.runs";

const base = makeRun(1, {}, { name: "baseline" });
const wideStop = makeRun(2, { config: { ...base.config, atr_mult: 3 }, metrics: makeMetrics({ total_return_pct: 20, trades: 7 }) }, { name: "wide stop" });

function pin(runs: PinnedRun[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(encodeRuns(runs)));
}

const stored = (): { runs: { name: string; hidden: boolean }[] } => JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");

function renderPage() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.endsWith("/config") ? config : url.endsWith("/signals") ? signals : null;
    return new Response(JSON.stringify(body), { status: body ? 200 : 404, headers: { "Content-Type": "application/json" } });
  });
  const router = createMemoryRouter([{ path: "/compare", element: <ComparePage /> }], { initialEntries: ["/compare"] });
  render(
    <PinnedRunsProvider>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </PinnedRunsProvider>,
  );
}

const table = (name: string) => screen.getByRole("table", { name });

describe("ComparePage", () => {
  beforeEach(() => vi.mocked(downloadFile).mockClear());

  it("explains how to pin when nothing is pinned", () => {
    renderPage();
    expect(screen.getByText("No pinned runs yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
  });

  it("shows only differing parameters, the best metrics and one curve per run", async () => {
    pin([base, wideStop]);
    renderPage();

    const parameters = table("Parameters of the pinned runs");
    expect(await within(parameters).findByText("Stop distance")).toBeInTheDocument();
    expect(within(parameters).getAllByRole("row")).toHaveLength(2);
    expect(within(parameters).queryByText("Ticker")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(within(table("Parameters of the pinned runs")).getByText("Ticker")).toBeInTheDocument();

    const totalReturn = within(table("Metrics of the pinned runs")).getByRole("row", { name: /Total return/ });
    expect(within(totalReturn).getAllByRole("cell")[1]).toHaveTextContent("+20.00% (best)");
    expect(screen.getByRole("img", { name: "Return of the pinned runs since their first bar" })).toHaveTextContent("#1 baseline | #2 wide stop");
    expect(within(screen.getByRole("article", { name: "Run 2" })).getByText("Only 7 trades: too few to trust the metrics.")).toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: "Run 1" })).getByRole("link", { name: "Open in Backtest" })).toHaveAttribute(
      "href",
      "/backtest?ticker=SPY&signal=connors_rsi2_long&eng=vectorized",
    );
  });

  it("hides, renames and removes runs and keeps the change in storage", async () => {
    pin([base, wideStop]);
    renderPage();
    const second = screen.getByRole("article", { name: "Run 2" });

    await userEvent.click(within(second).getByRole("button", { name: "Hide" }));
    expect(screen.getByRole("img", { name: /Return of the pinned runs/ })).toHaveTextContent(/^#1 baseline$/);
    expect(screen.getByText("Show at least two runs to see what differs.")).toBeInTheDocument();
    expect(stored().runs[1]?.hidden).toBe(true);

    const name = within(screen.getByRole("article", { name: "Run 1" })).getByRole("textbox", { name: "Name of run 1" });
    await userEvent.clear(name);
    await userEvent.type(name, "RSI2 default{Enter}");
    expect(stored().runs[0]?.name).toBe("RSI2 default");

    await userEvent.click(within(second).getByRole("button", { name: "Remove" }));
    expect(screen.queryByRole("article", { name: "Run 2" })).not.toBeInTheDocument();
    expect(stored().runs).toHaveLength(1);
  });

  it("removes all runs only after confirmation", async () => {
    pin([base, wideStop]);
    renderPage();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);

    await userEvent.click(screen.getByRole("button", { name: "Remove all" }));
    expect(screen.getAllByRole("article")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Remove all" }));
    expect(confirm).toHaveBeenCalledWith("Remove all 2 pinned runs? Export them first if you want a backup.");
    expect(screen.getByText("No pinned runs yet")).toBeInTheDocument();
  });

  it("exports the runs and imports them back without duplicates", async () => {
    pin([base]);
    renderPage();

    await userEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    const [filename, content, type] = vi.mocked(downloadFile).mock.calls[0] ?? [];
    expect(filename).toMatch(/^tradescan-runs-\d{4}-\d{2}-\d{2}\.json$/);
    expect(type).toBe("application/json");
    expect(JSON.parse(content ?? "")).toEqual(encodeRuns([base]));

    const file = JSON.stringify(encodeRuns([base, wideStop]));
    await userEvent.upload(screen.getByLabelText("Runs file to import"), new File([file], "runs.json", { type: "application/json" }));
    expect(await screen.findByText("Imported 1 run. 1 run already pinned.")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("reports an invalid import file", async () => {
    renderPage();
    await userEvent.upload(screen.getByLabelText("Runs file to import"), new File(["{"], "runs.json", { type: "application/json" }));
    expect(await screen.findByText("Import failed: The file is not valid JSON")).toBeInTheDocument();
  });

  it("reports saved runs it cannot read", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, runs: [{ id: 1 }] }));
    renderPage();
    expect(screen.getByRole("alert")).toHaveTextContent('Pinned runs saved in this browser could not be read (Run 1 has an invalid "id").');
  });
});
