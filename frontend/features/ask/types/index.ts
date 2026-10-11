import { z } from "zod";

/** A passage the Answer may cite as `[n]` (the `citations` event). */
export const citedPassageSchema = z.object({
  n: z.number(),
  chunk_id: z.string(),
  document_id: z.string(),
  document_name: z.string(),
  page_number: z.number(),
  text: z.string(),
});

export type CitedPassage = Readonly<z.infer<typeof citedPassageSchema>>;

export const citationsEventSchema = z.object({
  passages: z.array(citedPassageSchema),
});

export const answerDeltaEventSchema = z.object({ text: z.string() });

/** The stream's last event. `credits_charged` is rounded up. */
export const askDoneEventSchema = z.object({
  ask_id: z.string(),
  status: z.enum(["completed", "cut_off", "failed", "no_chunks"]),
  credits_charged: z.number(),
  balance_credits: z.number(),
  reranked: z.boolean(),
  degraded: z.boolean(),
});

export type AskDone = Readonly<z.infer<typeof askDoneEventSchema>>;

/** One event of POST /asks's stream, in the order they arrive. */
export type AskEvent =
  | Readonly<{ type: "citations"; passages: readonly CitedPassage[] }>
  | Readonly<{ type: "answer_delta"; text: string }>
  | Readonly<{ type: "done"; done: AskDone }>;
