import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router";

import { Layout } from "./components/Layout";
import { EmptyState, Loading } from "./components/ui";
import { AccountProvider } from "./state/account";
import { PinnedRunsProvider } from "./state/pinnedRuns";
import { ThemeProvider } from "./state/theme";

// Pages load on demand, so the chart library only downloads with the first page that needs it.
const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    hydrateFallbackElement: <Loading message="Loading…" />,
    children: [
      { index: true, lazy: async () => ({ Component: (await import("./pages/ScanPage")).ScanPage }) },
      { path: "backtest", lazy: async () => ({ Component: (await import("./pages/BacktestPage")).BacktestPage }) },
      { path: "edge", lazy: async () => ({ Component: (await import("./pages/EdgePage")).EdgePage }) },
      { path: "compare", lazy: async () => ({ Component: (await import("./pages/ComparePage")).ComparePage }) },
      { path: "signals", lazy: async () => ({ Component: (await import("./pages/SignalsPage")).SignalsPage }) },
      { path: "*", element: <EmptyState title="Page not found" /> },
    ],
  },
]);

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });

export function App() {
  return (
    <ThemeProvider>
      <AccountProvider>
        <PinnedRunsProvider>
          <QueryClientProvider client={queryClient}>
            <RouterProvider router={router} />
          </QueryClientProvider>
        </PinnedRunsProvider>
      </AccountProvider>
    </ThemeProvider>
  );
}
