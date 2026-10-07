import type { HighlightSegment } from "../types";

const NAMED: Readonly<Record<string, string>> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
};

const decode = (text: string) =>
  text.replace(
    /&(?:amp|lt|gt|quot);|&#x([0-9a-fA-F]+);|&#(\d+);/g,
    (entity, hex, dec) => {
      if (hex !== undefined) return String.fromCodePoint(parseInt(hex, 16));
      if (dec !== undefined) return String.fromCodePoint(Number(dec));
      return NAMED[entity];
    },
  );

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
