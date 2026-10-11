"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchCreditBalance } from "./fetch_credit_balance";

export const creditBalanceQueryKey = (tenantId: string) =>
  ["credit-balance", tenantId] as const;

/** The Tenant's Credit Balance, fetched client-side so an Ask can refresh it. */
export function useCreditBalance(tenantId: string) {
  return useQuery({
    queryKey: creditBalanceQueryKey(tenantId),
    queryFn: () => fetchCreditBalance(tenantId),
  });
}
