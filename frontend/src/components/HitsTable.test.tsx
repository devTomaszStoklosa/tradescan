import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { makeHit } from "../test/fixtures";
import { HitsTable } from "./HitsTable";

const tickersInOrder = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[0]!.textContent);

describe("HitsTable", () => {
  const hits = [
    makeHit({ ticker: "LOW", score: { total: 1, signals: 1, trend: 0, weekly: 0, relative_strength: 0 } }),
    makeHit({ ticker: "HIGH", score: { total: 5, signals: 2, trend: 1, weekly: 1, relative_strength: 1 } }),
    makeHit({ ticker: "MID", score: { total: 3, signals: 1, trend: 1, weekly: 1, relative_strength: 0 }, edge: null }),
  ];

  it("sorts by score, then by any sortable column", async () => {
    render(<HitsTable hits={hits} onSelect={() => {}} selectedKey={null} />);
    expect(tickersInOrder()).toEqual(["HIGH", "MID", "LOW"]);

    await userEvent.click(screen.getByRole("button", { name: /Ticker/ }));
    expect(tickersInOrder()).toEqual(["MID", "LOW", "HIGH"]);
    await userEvent.click(screen.getByRole("button", { name: /Ticker/ }));
    expect(tickersInOrder()).toEqual(["HIGH", "LOW", "MID"]);
  });

  it("shows signals, risk levels and edge, and selects rows by click or keyboard", async () => {
    const onSelect = vi.fn();
    render(<HitsTable hits={hits} onSelect={onSelect} selectedKey={null} />);
    expect(screen.getAllByText("donchian_breakout")).toHaveLength(3);
    expect(screen.getAllByText("192.00")[0]).toHaveClass("text-down");
    expect(screen.getByText("no history")).toBeInTheDocument();

    await userEvent.click(screen.getByText("HIGH"));
    expect(onSelect).toHaveBeenCalledWith(hits[1]);

    screen.getAllByRole("row")[2]!.focus();
    await userEvent.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith(hits[2]);
  });
});
