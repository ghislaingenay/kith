import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Client-driven server interaction only (mutations, polling) — see
        // context/coding-standards.md §5. A short staleTime avoids refetch
        // storms for the sparse client-side queries this app has.
        staleTime: 60 * 1000,
      },
    },
  });
}
