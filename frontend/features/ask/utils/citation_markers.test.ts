import { describe, expect, it } from "vitest";

import { renumberCitations, splitCitationMarkers, stripCitationMarkers } from "./citation_markers";

describe("splitCitationMarkers", () => {
  it("splits the Answer into text and the markers of known sources, dropping the space before each", () => {
    expect(splitCitationMarkers("Due in 30 days [1], or 60 [2].", new Set([1, 2]))).toEqual([
      { text: "Due in 30 days" },
      { n: 1 },
      { text: ", or 60" },
      { n: 2 },
      { text: "." },
    ]);
  });

  it("keeps a marker for a number with no source as plain text", () => {
    expect(splitCitationMarkers("Due [7].", new Set([1, 2]))).toEqual([{ text: "Due [7]." }]);
  });

  it("keeps the space before a marker that stays text", () => {
    expect(splitCitationMarkers("Due [7] [1].", new Set([1]))).toEqual([
      { text: "Due [7]" },
      { n: 1 },
      { text: "." },
    ]);
  });

  it("splits adjacent markers", () => {
    expect(splitCitationMarkers("Due[1][2]", new Set([1, 2]))).toEqual([
      { text: "Due" },
      { n: 1 },
      { n: 2 },
    ]);
  });

  it("leaves a marker still streaming in as text", () => {
    expect(splitCitationMarkers("Due [1", new Set([1]))).toEqual([{ text: "Due [1" }]);
  });

  it("returns nothing for an empty Answer", () => {
    expect(splitCitationMarkers("", new Set([1]))).toEqual([]);
  });
});

describe("stripCitationMarkers", () => {
  it("removes every marker and the space before it", () => {
    expect(stripCitationMarkers("Due in 30 days [1], or 60 [2][7].")).toBe(
      "Due in 30 days, or 60.",
    );
  });

  it("keeps brackets that are not markers", () => {
    expect(stripCitationMarkers("See [note] and [ 1 ].")).toBe("See [note] and [ 1 ].");
  });
});

describe("renumberCitations", () => {
  const passage = (n: number) => ({
    n,
    chunk_id: `c${n}`,
    document_id: "d1",
    document_name: "contract.pdf",
    page_number: n,
    text: `Passage ${n}`,
  });
  const FIVE = [1, 2, 3, 4, 5].map(passage);

  it("keeps only the marked passages, numbered in the order the Answer marks them", () => {
    const { answer, passages } = renumberCitations("Due in 30 days [4], or 60 [2].", FIVE);

    expect(answer).toBe("Due in 30 days [1], or 60 [2].");
    expect(passages).toEqual([
      { ...passage(4), n: 1 },
      { ...passage(2), n: 2 },
    ]);
  });

  it("gives a passage marked twice one number", () => {
    const { answer, passages } = renumberCitations("Due [2], then [3][2].", FIVE);

    expect(answer).toBe("Due [1], then [2][1].");
    expect(passages.map((p) => p.chunk_id)).toEqual(["c2", "c3"]);
  });

  it("leaves a marker for a number with no passage as it is", () => {
    const { answer, passages } = renumberCitations("Due [7] or [5].", FIVE);

    expect(answer).toBe("Due [7] or [1].");
    expect(passages.map((p) => p.chunk_id)).toEqual(["c5"]);
  });

  it("keeps no passages when the Answer marks none", () => {
    expect(renumberCitations("Not found.", FIVE)).toEqual({ answer: "Not found.", passages: [] });
  });
});
