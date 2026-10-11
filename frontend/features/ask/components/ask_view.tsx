import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api_client";

import type { AskState } from "../hooks/use_ask";
import type { CitedPassage } from "../types";

/** An Ask's Citations, then its Answer as plain text (never injected as HTML). */
export function AskView({ state }: { readonly state: AskState }) {
  if (state.phase === "idle") return null;
  return (
    <div className="space-y-4">
      {state.passages === null ? (
        state.phase === "streaming" && <LoadingCitations />
      ) : (
        <ol aria-label="Citations" className="grid gap-2 sm:grid-cols-2">
          {state.passages.map((passage) => (
            <li key={passage.chunk_id}>
              <CitationCard passage={passage} />
            </li>
          ))}
        </ol>
      )}
      {state.passages !== null && (
        <p aria-label="Answer" aria-live="polite" className="whitespace-pre-wrap text-sm">
          {state.answer}
        </p>
      )}
      {state.done?.status === "cut_off" && (
        <p role="status" className="text-sm text-muted-foreground">
          The answer was interrupted. {state.done.credits_charged}{" "}
          {state.done.credits_charged === 1 ? "credit was" : "credits were"} used for what
          the AI had already read and written.
        </p>
      )}
      {state.phase === "failed" && <AskFailure state={state} />}
    </div>
  );
}

function CitationCard({ passage }: { readonly passage: CitedPassage }) {
  return (
    <div className="h-full rounded-lg border px-3 py-2">
      <p className="text-sm font-medium">
        <span className="mr-2 text-muted-foreground">[{passage.n}]</span>
        {passage.document_name}
        <span className="ml-2 font-normal text-muted-foreground">
          Page {passage.page_number}
        </span>
      </p>
      <p className="mt-1 line-clamp-3 whitespace-pre-line text-sm text-muted-foreground">
        {passage.text}
      </p>
    </div>
  );
}

function LoadingCitations() {
  return (
    <div role="status" aria-label="Finding passages" className="space-y-3">
      {[0, 1].map((row) => (
        <Skeleton key={row} className="h-16 w-full" />
      ))}
    </div>
  );
}

function AskFailure({ state }: { readonly state: AskState }) {
  return (
    <p role="alert" className="text-sm text-destructive">
      {failureMessage(state)}
    </p>
  );
}

function failureMessage({ error, done }: AskState): string {
  // The Ask ended failed in its `done`: the model was down or erred, and
  // `done` says what it cost.
  if (done?.status === "failed" && done.credits_charged === 0) {
    return "The answer failed. No credits were used. Try again.";
  }
  const status = error instanceof ApiError ? error.status : null;
  if (status === 429) return "You are asking too fast. Wait a moment and try again.";
  if (status === 503) return "Answers are unavailable right now.";
  return "The answer failed. Try again.";
}
