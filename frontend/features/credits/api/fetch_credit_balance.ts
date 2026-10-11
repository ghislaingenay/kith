import { apiFetch } from "@/lib/api_client";

import { creditBalanceSchema, type CreditBalance } from "../types";

/** GET /credit-balance: the Tenant's Credit Balance (ADR-0017). */
export async function fetchCreditBalance(tenantId: string): Promise<CreditBalance> {
  const data = await apiFetch("/api/v1/credit-balance", {
    credentials: "include",
    headers: { "X-Tenant-ID": tenantId },
  });
  return creditBalanceSchema.parse(data);
}
