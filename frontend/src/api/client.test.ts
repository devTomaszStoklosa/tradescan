import { describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./client";

const respond = (status: number, body: unknown) =>
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

describe("api client", () => {
  it("posts JSON and returns the parsed body", async () => {
    const fetch = respond(200, { hits: [] });
    await expect(api.scan({ watchlist: "etf" })).resolves.toEqual({ hits: [] });
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe("/api/scan");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ watchlist: "etf" });
  });

  it("surfaces the server's error detail", async () => {
    respond(400, { detail: "No data for ZZZ" });
    await expect(api.backtest({ ticker: "ZZZ", signal: "golden_cross" })).rejects.toMatchObject({ status: 400, message: "No data for ZZZ" });
  });

  it("formats validation errors", async () => {
    respond(422, { detail: [{ loc: ["body", "fresh_bars"], msg: "Input should be greater than or equal to 1" }] });
    await expect(api.scan({ watchlist: "etf", fresh_bars: 0 })).rejects.toThrow("fresh_bars: Input should be greater than or equal to 1");
  });

  it("explains when the server is down", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await api.config().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toMatch(/tradescan serve/);
  });

  it("encodes tickers and repeats signal params for charts", async () => {
    const fetch = respond(200, {});
    await api.chart("^GSPC", ["golden_cross", "death_cross"], "1y");
    expect(fetch.mock.calls[0]![0]).toBe("/api/chart/%5EGSPC?signals=golden_cross&signals=death_cross&period=1y");
  });
});
