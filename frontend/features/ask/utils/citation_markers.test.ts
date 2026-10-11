import { describe, expect, it } from "vitest";

import { citedNumbers, splitCitationMarkers, stripCitationMarkers } from "./citation_markers";

describe("splitCitationMarkers", () => {
  it("splits the Answer into text and the markers of known sources", () => {
    expect(splitCitationMarkers("Due in 30 days [1], or 60 [2].", new Set([1, 2]))).toEqual([
      { text: "Due in 30 days " },
      { n: 1 },
      { text: ", or 60 " },
      { n: 2 },
      { text: "." },
    ]);
  });

  it("keeps a marker for a number with no source as plain text", () => {
    expect(splitCitationMarkers("Due [7].", new Set([1, 2]))).toEqual([{ text: "Due [7]." }]);
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

describe("citedNumbers", () => {
  it("lists the numbers the Answer marks", () => {
    expect(citedNumbers("Due [2], or [2] and [7].")).toEqual(new Set([2, 7]));
  });
});
