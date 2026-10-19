import { describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./client";
import { requestBody } from "../test/fetch";

const respond = (status: number, body: unknown) =>
  vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

describe("api client", () => {
  it("posts JSON and returns the parsed body", async () => {
    const fetch = respond(200, { hits: [] });
    await expect(api.scan({ watchlist: "etf" })).resolves.toEqual({ hits: [] });
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe("/api/scan");
    expect(init?.method).toBe("POST");
    expect(requestBody(init)).toEqual({ watchlist: "etf" });
  });

  it("surfaces the server's error detail", async () => {
    respond(400, { detail: "No data for ZZZ" });
    await expect(api.backtest({ ticker: "ZZZ", signal: "golden_cross" })).rejects.toMatchObject({
      status: 400,
      message: "No data for ZZZ",
    });
  });

  it("formats validation errors", async () => {
    respond(422, { detail: [{ loc: ["body", "horizons", 0], msg: "Input should be a valid integer" }] });
    await expect(api.edge({ watchlist: "etf", horizons: [1.5], min_events: 0 })).rejects.toThrow(
      "horizons.0: Input should be a valid integer",
    );
  });

  it("explains when the server is down", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await api.config().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toMatch(/tradescan serve/);
  });

  it("posts chart requests with the signals' parameters", async () => {
    const fetch = respond(200, {});
    const body = {
      ticker: "^GSPC",
      signals: ["golden_cross"],
      signal_params: { golden_cross: { fast: 20 } },
      period: "1y",
    };
    await api.chart(body);
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe("/api/chart");
    expect(requestBody(init)).toEqual(body);
  });

  it("patches and deletes a pinned run by its id", async () => {
    const fetch = respond(200, {});
    await api.updateRun("a/b", { hidden: true });
    const [url, init] = fetch.mock.calls[0]!;
    expect([url, init?.method, requestBody(init)]).toEqual(["/api/runs/a%2Fb", "PATCH", { hidden: true }]);

    fetch.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api.unpinRun("a/b")).resolves.toBeUndefined();
    const [, removal] = fetch.mock.calls[1]!;
    expect([removal?.method, removal?.body]).toEqual(["DELETE", undefined]);
  });
});
