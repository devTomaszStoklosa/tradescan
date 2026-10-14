import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import type { Values } from "../lib/overrides";
import { spec } from "../test/fixtures";
import { ParamFields } from "./ParamFields";

const SPECS = [
  spec("period", "Channel length", 20, [2, 300, 1], "int", { unit: "bars" }),
  spec("targets_r", "Targets", [2, 3], [0.25, 50, 0.25], "float_list"),
  spec("family_weights", "Family weights", { trend: 1, breakout: 1.5 }, [-10, 10, 0.5], "weights", { keys: ["trend", "breakout"] }),
];

function Harness({ initial = {}, seen }: { initial?: Values; seen: Values[] }) {
  const [values, setValues] = useState<Values>(initial);
  return (
    <ParamFields
      specs={SPECS}
      values={values}
      onChange={(next) => {
        seen.push(next);
        setValues(next);
      }}
    />
  );
}

describe("ParamFields", () => {
  it("shows defaults as placeholders and keeps only changed values", async () => {
    const seen: Values[] = [];
    render(<Harness seen={seen} />);
    const length = screen.getByLabelText("Channel length (bars)");
    expect(length).toHaveAttribute("placeholder", "20");
    expect(screen.queryByRole("button", { name: /reset/i })).not.toBeInTheDocument();

    await userEvent.type(length, "35");
    expect(seen.at(-1)).toEqual({ period: 35 });
    await userEvent.click(screen.getByRole("button", { name: "Reset Channel length to default" }));
    expect(seen.at(-1)).toEqual({});
    expect(length).toHaveValue(null);
  });

  it("parses lists and weights", async () => {
    const seen: Values[] = [];
    render(<Harness seen={seen} />);
    await userEvent.type(screen.getByLabelText("Targets"), "1.5, 4");
    expect(seen.at(-1)).toEqual({ targets_r: [1.5, 4] });
    expect(screen.getByLabelText("Targets")).toHaveValue("1.5, 4");

    await userEvent.type(screen.getByLabelText("Family weights: breakout"), "3");
    expect(seen.at(-1)).toEqual({ targets_r: [1.5, 4], family_weights: { breakout: 3 } });
  });

  it("flags values outside the allowed range", () => {
    render(<Harness seen={[]} initial={{ period: 1 }} />);
    expect(screen.getByLabelText("Channel length (bars)")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Allowed: 2–300")).toBeInTheDocument();
  });
});
