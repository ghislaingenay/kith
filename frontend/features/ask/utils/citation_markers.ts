/** A run of Answer text, or a `[n]` marker for one of the Answer's passages. */
export type AnswerSegment = Readonly<{ text: string }> | Readonly<{ n: number }>;

const MARKER = /\[(\d+)\]/g;

/** Splits the Answer around its `[n]` markers. A marker for a number not in
 * `passageNumbers` stays in the text, so it never becomes a broken link. */
export function splitCitationMarkers(
  answer: string,
  passageNumbers: ReadonlySet<number>,
): readonly AnswerSegment[] {
  const segments: AnswerSegment[] = [];
  let text = "";
  let last = 0;
  for (const match of answer.matchAll(MARKER)) {
    const n = Number(match[1]);
    if (!passageNumbers.has(n)) continue;
    text += answer.slice(last, match.index);
    if (text !== "") segments.push({ text });
    segments.push({ n });
    text = "";
    last = match.index + match[0].length;
  }
  text += answer.slice(last);
  if (text !== "") segments.push({ text });
  return segments;
}

/** The Answer with every `[n]` marker, and the spaces before it, removed. */
export function stripCitationMarkers(answer: string): string {
  return answer.replace(new RegExp(` *${MARKER.source}`, "g"), "");
}

/** The numbers the Answer marks with `[n]`. */
export function citedNumbers(answer: string): ReadonlySet<number> {
  return new Set(Array.from(answer.matchAll(MARKER), (match) => Number(match[1])));
}
