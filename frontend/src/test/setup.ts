import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// A page's first render in a file can take over a second while every worker is busy, past the 1000 ms default.
// Stays below the 5000 ms test timeout, so a wait that never succeeds still reports what it was waiting for.
configure({ asyncUtilTimeout: 3000 });

// jsdom lays nothing out, so it has no scrollIntoView.
Element.prototype.scrollIntoView = () => undefined;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});
