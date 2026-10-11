"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { creditBalanceQueryKey } from "@/features/credits";

import { streamAsk } from "../api/stream_ask";
import type { AskDone, CitedPassage } from "../types";

/** What the User sees of their latest Ask. `passages` is `null` until the
 * `citations` event arrives. */
export type AskState = Readonly<{
  phase: "idle" | "streaming" | "done" | "failed";
  passages: readonly CitedPassage[] | null;
  answer: string;
  done: AskDone | null;
  error: unknown;
}>;

const IDLE: AskState = {
  phase: "idle",
  passages: null,
  answer: "",
  done: null,
  error: null,
};

/** Runs one Ask at a time and refreshes the Credit Balance after each. Only
 * ever started by `ask()`, so a reload never charges again. */
export function useAsk(tenantId: string) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AskState>(IDLE);
  const controllerRef = useRef<AbortController | null>(null);

  // Leaving the page stops the Answer, so the model call stops too.
  useEffect(() => () => controllerRef.current?.abort(), []);

  const ask = useCallback(
    async (query: string) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ ...IDLE, phase: "streaming" });
      try {
        for await (const event of streamAsk(tenantId, query, controller.signal)) {
          if (event.type === "citations") {
            setState((current) => ({ ...current, passages: event.passages }));
          } else if (event.type === "answer_delta") {
            setState((current) => ({ ...current, answer: current.answer + event.text }));
          } else {
            setState((current) => ({ ...current, phase: "done", done: event.done }));
          }
        }
        // A stream that closes without `done` broke partway.
        setState((current) =>
          current.phase === "done" ? current : { ...current, phase: "failed" },
        );
      } catch (error) {
        if (controller.signal.aborted) return;
        setState((current) => ({ ...current, phase: "failed", error }));
      } finally {
        if (!controller.signal.aborted) {
          void queryClient.invalidateQueries({
            queryKey: creditBalanceQueryKey(tenantId),
          });
        }
      }
    },
    [queryClient, tenantId],
  );

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setState(IDLE);
  }, []);

  return { state, ask, reset };
}
