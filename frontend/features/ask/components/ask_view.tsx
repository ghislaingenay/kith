"use client";

import { useId, useState, type MouseEvent } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { env } from "@/config/env";
import { DocumentViewerDialog } from "@/features/document-viewer";
import { ApiError } from "@/lib/api_client";

import type { AskState } from "../hooks/use_ask";
import type { CitedPassage } from "../types";
import {
  renumberCitations,
  splitCitationMarkers,
  stripCitationMarkers,
} from "../utils/citation_markers";

/** An Ask's Citations, then its Answer as plain text (never injected as HTML).
 * Each `[n]` marker links to Citation card `n`, unless the env flags turn the
 * sources or the markers off. */
export function AskView({
  tenantId,
  state,
}: {
  readonly tenantId: string;
  readonly state: AskState;
}) {
  // Card ids for the markers' links, unique even with two AskViews on a page.
  const idPrefix = useId();
  // Local state, so closing the viewer leaves the Answer untouched.
  const [opened, setOpened] = useState<CitedPassage | null>(null);
  if (state.phase === "idle") return null;

  const showSources = env.NEXT_PUBLIC_ASK_SHOW_SOURCES;
  const showMarkers = showSources && env.NEXT_PUBLIC_ASK_CITATION_MARKERS;
  const cardId = (n: number) => `${idPrefix}-citation-${n}`;
  // No passages means the model was never asked (`no_chunks`).
  const hasPassages = state.passages !== null && state.passages.length > 0;
  // Until the Answer ends, the passages it will cite are unknown: the
  // Citations wait, and so do the markers.
  const isWriting = state.phase === "streaming" && state.done === null;
  // A completed Answer shows only the passages it cites; a failed or cut-off
  // one keeps every passage the AI read.
  const { answer, passages } =
    state.done?.status === "completed" && state.passages
      ? renumberCitations(state.answer, state.passages)
      : { answer: state.answer, passages: state.passages };

  return (
    <div className="space-y-4">
      {isWriting || passages === null ? (
        showSources && isWriting && <LoadingCitations />
      ) : (
        showSources &&
        passages.length > 0 && (
          <ol aria-label="Citations" className="grid gap-2 sm:grid-cols-2">
            {passages.map((passage) => (
              <li key={passage.chunk_id}>
                <CitationCard
                  id={cardId(passage.n)}
                  passage={passage}
                  onOpen={() => setOpened(passage)}
                />
              </li>
            ))}
          </ol>
        )
      )}
      {hasPassages && passages && (
        <p aria-label="Answer" aria-live="polite" className="whitespace-pre-wrap text-sm">
          {showMarkers && !isWriting ? (
            <MarkedAnswer answer={answer} passages={passages} cardId={cardId} />
          ) : (
            stripCitationMarkers(answer)
          )}
        </p>
      )}
      {state.done?.status === "no_chunks" && (
        <p role="status" className="text-sm text-muted-foreground">
          No passages in your Documents match this.
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
      {opened && (
        <DocumentViewerDialog
          tenantId={tenantId}
          documentId={opened.document_id}
          documentName={opened.document_name}
          initialPage={opened.page_number}
          open
          onOpenChange={(open) => {
            if (!open) setOpened(null);
          }}
        />
      )}
    </div>
  );
}

function MarkedAnswer({
  answer,
  passages,
  cardId,
}: {
  readonly answer: string;
  readonly passages: readonly CitedPassage[];
  readonly cardId: (n: number) => string;
}) {
  const passageNumbers = new Set(passages.map((passage) => passage.n));
  return splitCitationMarkers(answer, passageNumbers).map((segment, index) =>
    "text" in segment ? (
      segment.text
    ) : (
      <a
        key={index}
        href={`#${cardId(segment.n)}`}
        aria-label={`Citation ${segment.n}`}
        onClick={(event) => showCard(event, cardId(segment.n))}
        className="font-medium text-primary underline-offset-2 hover:underline"
      >
        [{segment.n}]
      </a>
    ),
  );
}

function CitationCard({
  id,
  passage,
  onOpen,
}: {
  readonly id: string;
  readonly passage: CitedPassage;
  readonly onOpen: () => void;
}) {
  return (
    <button
      id={id}
      type="button"
      onClick={onOpen}
      className="h-full w-full cursor-pointer rounded-lg border px-3 py-2 text-left hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring"
    >
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
    </button>
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
  // The Credit Balance refreshes after each Ask, so Ask AI then says who to ask.
  if (status === 402) return "No credits left.";
  if (status === 429) return "You are asking too fast. Wait a moment and try again.";
  if (status === 503) return "Answers are unavailable right now.";
  return "The answer failed. Try again.";
}

/** Scrolls Citation card `id` into view and focuses it, without a `#` in the
 * URL (the URL holds the Search). */
function showCard(event: MouseEvent, id: string) {
  event.preventDefault();
  const card = document.getElementById(id);
  card?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  card?.focus({ preventScroll: true });
}
