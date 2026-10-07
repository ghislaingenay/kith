import { describe, expect, it } from "vitest";

import { parseHighlight } from "./parse_highlights";

describe("parseHighlight", () => {
  it("turns markers into marked segments", () => {
    expect(parseHighlight("the <mark>cat</mark> sat")).toEqual([
      { text: "the ", marked: false },
      { text: "cat", marked: true },
      { text: " sat", marked: false },
    ]);
  });

  it("decodes the backend's escaping into plain text, never markup", () => {
    expect(parseHighlight("&lt;b&gt;R&amp;D&lt;/b&gt; <mark>it&#x27;s</mark>")).toEqual([
      { text: "<b>R&D</b> ", marked: false },
      { text: "it's", marked: true },
    ]);
  });
});
