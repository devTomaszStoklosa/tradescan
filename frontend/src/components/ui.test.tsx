import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FieldGroup, ToggleChip } from "./ui";

describe("FieldGroup", () => {
  it("presses nothing when its caption is clicked", async () => {
    const onClick = vi.fn();
    render(
      <FieldGroup label="Engines" hint="At least one">
        <ToggleChip active={false} onClick={onClick}>
          vectorized
        </ToggleChip>
      </FieldGroup>,
    );

    await userEvent.click(screen.getByText("Engines"));
    expect(onClick).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "vectorized" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("names its group by the caption", () => {
    render(
      <FieldGroup label="Engines">
        <ToggleChip active onClick={vi.fn()}>
          vectorized
        </ToggleChip>
      </FieldGroup>,
    );

    const group = screen.getByRole("group", { name: "Engines" });
    expect(within(group).getByRole("button", { name: "vectorized" })).toBeInTheDocument();
  });
});
