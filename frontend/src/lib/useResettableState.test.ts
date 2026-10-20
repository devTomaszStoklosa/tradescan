import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useResettableState } from "./useResettableState";

describe("useResettableState", () => {
  it("keeps local changes until the value changes", () => {
    const { result, rerender } = renderHook(({ value }) => useResettableState(value), { initialProps: { value: "a" } });
    act(() => result.current[1]("typed"));
    rerender({ value: "a" });
    expect(result.current[0]).toBe("typed");
    rerender({ value: "b" });
    expect(result.current[0]).toBe("b");
  });

  it("starts over when the reset key changes, even to an equal value", () => {
    const { result, rerender } = renderHook(({ value, key }) => useResettableState(value, key), {
      initialProps: { value: "vectorized", key: {} },
    });
    act(() => result.current[1]("cerebro"));
    rerender({ value: "vectorized", key: {} });
    expect(result.current[0]).toBe("vectorized");
  });
});
