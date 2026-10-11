"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

import { useCreditBalance } from "../api/use_credit_balance";
import type { CreditBalance as CreditBalanceData } from "../types";

/** The sidebar's "N credits left", amber when low; renders nothing until the
 * balance is known. */
export function CreditBalance({ tenantId }: { readonly tenantId: string }) {
  const { data: balance } = useCreditBalance(tenantId);
  if (!balance) {
    return null;
  }

  const state = balanceState(balance);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-balance={state}
          className={`truncate px-2 text-left text-sm ${STATE_CLASSES[state]}`}
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
  low: "text-amber-600 dark:text-amber-400",
  exhausted: "text-amber-600 dark:text-amber-400",
};

type BalanceState = "normal" | "low" | "exhausted";
