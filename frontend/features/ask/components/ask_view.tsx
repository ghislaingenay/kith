"use client";

import { useState } from "react";

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

/** An Ask's Answer as a cited note: the Answer as plain text (never injected
 * as HTML) with superscript Citation numbers, then a numbered footnote per
 * cited passage. A number or a footnote opens the Document at its page. The
 * env flags can turn the sources, or just the numbers, off. */
export function AskView({
  tenantId,
  state,
}: {
  readonly tenantId: string;
  readonly state: AskState;
}) {
  // Local state, so closing the viewer leaves the Answer untouched.
  const [opened, setOpened] = useState<CitedPassage | null>(null);
  if (state.phase === "idle") return null;

  const showSources = env.NEXT_PUBLIC_ASK_SHOW_SOURCES;
  const showMarkers = showSources && env.NEXT_PUBLIC_ASK_CITATION_MARKERS;
  // No passages means the model was never asked (`no_chunks`).
  const hasPassages = state.passages !== null && state.passages.length > 0;
  // Until the Answer ends, the passages it will cite are unknown: the
  // footnotes wait, and so do the numbers.
  const isWriting = state.phase === "streaming" && state.done === null;
  // A completed Answer shows only the passages it cites; a failed or cut-off
  // one keeps every passage the AI read.
  const { answer, passages } =
    state.done?.status === "completed" && state.passages
      ? renumberCitations(state.answer, state.passages)
      : { answer: state.answer, passages: state.passages };

  return (
    <div className="space-y-6">
      {isWriting && state.answer === "" && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          Finding passages…
        </p>
      )}
      {hasPassages && passages && (
        <p
          aria-label="Answer"
          aria-live="polite"
          className="whitespace-pre-wrap font-serif text-lg leading-relaxed"
        >
          {showMarkers && !isWriting ? (
            <MarkedAnswer answer={answer} passages={passages} onOpen={setOpened} />
          ) : (
            stripCitationMarkers(answer)
          )}
        </p>
      )}
      {showSources && !isWriting && passages !== null && passages.length > 0 && (
        <ol aria-label="Citations" className="space-y-1 border-t pt-4">
          {passages.map((passage) => (
            <li key={passage.chunk_id}>
              <Footnote passage={passage} onOpen={() => setOpened(passage)} />
            </li>
          ))}
        </ol>
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
  onOpen,
}: {
  readonly answer: string;
  readonly passages: readonly CitedPassage[];
  readonly onOpen: (passage: CitedPassage) => void;
}) {
  const byNumber = new Map(passages.map((passage) => [passage.n, passage]));
  return splitCitationMarkers(answer, new Set(byNumber.keys())).map((segment, index) =>
    "text" in segment ? (
      segment.text
    ) : (
      <sup key={index}>
        <button
          type="button"
          aria-label={`Citation ${segment.n}`}
          onClick={() => onOpen(byNumber.get(segment.n)!)}
          className="cursor-pointer px-0.5 font-sans text-xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
        >
          {segment.n}
        </button>
      </sup>
    ),
  );
}

function Footnote({
  passage,
  onOpen,
}: {
  readonly passage: CitedPassage;
  readonly onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex w-full cursor-pointer gap-3 rounded-md px-2 py-2 text-left hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
    >
      <span className="w-4 shrink-0 pt-0.5 text-right font-mono text-xs text-muted-foreground">
        {passage.n}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm">
          <span className="font-medium text-primary underline-offset-4 group-hover:underline">
            {passage.document_name}
          </span>
          <span className="ml-2 font-mono text-xs text-muted-foreground">
            p. {passage.page_number}
          </span>
        </span>
        <span className="mt-0.5 line-clamp-2 whitespace-pre-line font-serif text-sm text-muted-foreground">
          {passage.text}
        </span>
      </span>
    </button>
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
