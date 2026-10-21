import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EnginePicker } from "./EnginePicker";

describe("EnginePicker", () => {
  it("shows the chosen engines as pressed", () => {
    render(<EnginePicker available={["vectorized", "cerebro"]} value={["cerebro"]} onChange={vi.fn()} />);

    expect(screen.getByRole("button", { name: "cerebro" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "vectorized" })).toHaveAttribute("aria-pressed", "false");
  });

  it("adds an engine that is off and drops one that is on", async () => {
    const onChange = vi.fn();
    render(<EnginePicker available={["vectorized", "cerebro"]} value={["vectorized"]} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: "cerebro" }));
    expect(onChange).toHaveBeenLastCalledWith(["vectorized", "cerebro"]);

    await userEvent.click(screen.getByRole("button", { name: "vectorized" }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });
});
