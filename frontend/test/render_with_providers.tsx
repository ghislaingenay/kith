import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";

/** Wraps `render` with a fresh, retry-disabled QueryClient — every
 * component under test that uses TanStack Query needs the provider, and
 * disabling retries keeps error-state tests from waiting out a retry
 * backoff. Pass a client to inspect its cache. */
export function renderWithProviders(
  ui: ReactElement,
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  }),
): RenderResult {
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}
