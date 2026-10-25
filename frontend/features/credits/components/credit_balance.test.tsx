import { QueryClient } from "@tanstack/react-query";
import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/render_with_providers";

import { creditBalanceQueryKey } from "../api/use_credit_balance";
import { CreditBalance } from "./credit_balance";

const API_URL = "http://localhost:8000/api/v1";
const TENANT_ID = "tenant-1";
const LOAD_FAILED = "Your credit balance couldn't load.";

function renderBalance(queryClient?: QueryClient) {
  return renderWithProviders(
    <TooltipProvider>
      <CreditBalance tenantId={TENANT_ID} />
      <Toaster />
    </TooltipProvider>,
    queryClient,
  );
}

describe("CreditBalance", () => {
  it("shows how many credits are left", async () => {
    server.use(
      http.get(`${API_URL}/credit-balance`, () =>
        HttpResponse.json({ credits: 212, tokens: 212_000, is_low: false, is_exhausted: false }),
      ),
    );

    renderBalance();

    expect(await screen.findByRole("button", { name: "212 credits left" })).toBeInTheDocument();
  });

  it("shows a toast once when the balance can't load", async () => {
    let calls = 0;
    server.use(
      http.get(`${API_URL}/credit-balance`, () => {
        calls += 1;
        return HttpResponse.json(
          { error: "Internal", message: "database exploded" },
          { status: 500 },
        );
      }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    renderBalance(queryClient);

    expect(await screen.findByText(LOAD_FAILED)).toBeInTheDocument();
    expect(screen.queryByText("database exploded")).not.toBeInTheDocument();

    await queryClient.refetchQueries({ queryKey: creditBalanceQueryKey(TENANT_ID) });
    await waitFor(() => expect(calls).toBe(2));
    expect(screen.getAllByText(LOAD_FAILED)).toHaveLength(1);
  });
});
