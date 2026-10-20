/** Read what the code under test passed to a mocked `fetch`. */

/** The URL a `fetch` call asked for. */
export function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  return input instanceof URL ? input.href : input.url;
}

/** The JSON body a `fetch` call sent; the caller states its type. */
export function requestBody(init: RequestInit | undefined): unknown {
  if (typeof init?.body !== "string") throw new Error("Expected a JSON request body");
  return JSON.parse(init.body);
}
