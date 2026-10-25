import type { CitedPassage } from "../types";

/** A run of Answer text, or a `[n]` marker for one of the Answer's passages. */
export type AnswerSegment = Readonly<{ text: string }> | Readonly<{ n: number }>;

const MARKER = /\[(\d+)\]/g;

/** Splits the Answer around its `[n]` markers, dropping the spaces before
 * each, so its number sits against the word it cites. A marker for a number
 * not in `passageNumbers` stays in the text, so it never becomes a broken
 * link. */
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
    text = (text + answer.slice(last, match.index)).replace(/ +$/, "");
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

/** A finished Answer's Citations: only the passages its `[n]` markers mark,
 * renumbered 1, 2, 3… in the order the Answer first marks them, and the Answer
 * with its markers renumbered to match. A marker for a number not in
 * `passages` is left as it is. */
export function renumberCitations(
  answer: string,
  passages: readonly CitedPassage[],
): Readonly<{ answer: string; passages: readonly CitedPassage[] }> {
  const byNumber = new Map(passages.map((passage) => [passage.n, passage]));
  const renumbered = new Map<number, number>();
  const cited: CitedPassage[] = [];
  for (const match of answer.matchAll(MARKER)) {
    const n = Number(match[1]);
    const passage = byNumber.get(n);
    if (passage === undefined || renumbered.has(n)) continue;
    cited.push({ ...passage, n: cited.length + 1 });
    renumbered.set(n, cited.length);
  }
  return {
    answer: answer.replace(MARKER, (marker, n: string) => {
      const newN = renumbered.get(Number(n));
      return newN === undefined ? marker : `[${newN}]`;
    }),
    passages: cited,
  };
}
