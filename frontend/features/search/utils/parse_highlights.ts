import type { HighlightSegment } from "../types";

const ENTITIES: Readonly<Record<string, string>> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
};

const decode = (text: string) =>
  text.replace(/&(?:amp|lt|gt|quot|#x27|#39);/g, (entity) => ENTITIES[entity]);

/** Splits an escaped highlight fragment on its `<mark>` markers into plain
 * text runs. The caller renders them as React text, so nothing is ever
 * injected as HTML. */
export function parseHighlight(fragment: string): HighlightSegment[] {
  const segments: HighlightSegment[] = [];
  let marked = false;
  for (const part of fragment.split(/(<mark>|<\/mark>)/)) {
    if (part === "<mark>") marked = true;
    else if (part === "</mark>") marked = false;
    else if (part !== "") segments.push({ text: decode(part), marked });
  }
  return segments;
}
