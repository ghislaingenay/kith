"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

import { useCreditBalance } from "../api/use_credit_balance";
import type { CreditBalance as CreditBalanceData } from "../types";

/** The sidebar's "N credits left", amber when low; a skeleton while the
 * balance loads, and nothing if it can't be fetched. */
export function CreditBalance({ tenantId }: { readonly tenantId: string }) {
  const { data: balance, isPending, isError } = useCreditBalance(tenantId);
  if (isPending) {
    return (
      <Skeleton role="status" aria-label="Loading credits" className="mx-2 h-4 w-24" />
    );
  }
  if (isError) {
    return null;
  }

  const state = balanceState(balance);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-balance={state}
          className={`truncate px-2 text-left font-mono text-xs ${STATE_CLASSES[state]}`}
        >
          {balanceLabel(balance)}
        </button>
      </TooltipTrigger>
      <TooltipContent side="right">{CREDITS_EXPLANATION}</TooltipContent>
    </Tooltip>
  );
}

function balanceState(balance: CreditBalanceData): BalanceState {
  if (balance.is_exhausted) return "exhausted";
  if (balance.is_low) return "low";
  return "normal";
}

function balanceLabel(balance: CreditBalanceData): string {
  if (balance.is_exhausted) return "No credits left";
  return `${balance.credits} ${balance.credits === 1 ? "credit" : "credits"} left`;
}

const CREDITS_EXPLANATION =
  "Each Ask uses credits for the text the AI reads and writes, about 4 for a typical Ask. 1 credit = 1,000 tokens. Search is free.";

const STATE_CLASSES: Record<BalanceState, string> = {
  normal: "text-sidebar-foreground/70",
  low: "text-warning",
  exhausted: "text-warning",
};

type BalanceState = "normal" | "low" | "exhausted";
