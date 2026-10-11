import { apiStream } from "@/lib/api_client";

import {
  answerDeltaEventSchema,
  askDoneEventSchema,
  citationsEventSchema,
  type AskEvent,
} from "../types";
import { parseServerSentEvents } from "../utils/parse_server_sent_events";

/** POST /asks: the Answer to a Query, event by event. A refusal before the
 * stream (403, 422, 429, 503…) throws an `ApiError`. */
export async function* streamAsk(
  tenantId: string,
  query: string,
  signal: AbortSignal,
): AsyncGenerator<AskEvent> {
  const body = await apiStream("/api/v1/asks", {
    method: "POST",
    credentials: "include",
    headers: { "X-Tenant-ID": tenantId },
    body: { query },
    signal,
  });
  for await (const { event, data } of parseServerSentEvents(body)) {
    const payload: unknown = JSON.parse(data);
    if (event === "citations") {
      yield { type: "citations", ...citationsEventSchema.parse(payload) };
    } else if (event === "answer_delta") {
      yield { type: "answer_delta", ...answerDeltaEventSchema.parse(payload) };
    } else if (event === "done") {
      yield { type: "done", done: askDoneEventSchema.parse(payload) };
    }
  }
}
