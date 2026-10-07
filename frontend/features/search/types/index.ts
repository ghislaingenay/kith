import { z } from "zod";

/** One ranked passage (POST /search). `highlights` are fragments of `text`,
 * HTML-escaped, with each match wrapped in `<mark>`; empty when none matched. */
export const searchResultSchema = z.object({
  chunk_id: z.string(),
  document_id: z.string(),
  document_name: z.string(),
  document_status: z.string(),
  page_number: z.number(),
  text: z.string(),
  highlights: z.array(z.string()),
});

export type SearchResult = Readonly<z.infer<typeof searchResultSchema>>;

export const searchResponseSchema = z.object({
  degraded: z.boolean(),
  results: z.array(searchResultSchema),
});

export type SearchResponse = Readonly<z.infer<typeof searchResponseSchema>>;

/** A run of passage text, marked when the Query matched it. */
export type HighlightSegment = Readonly<{ text: string; marked: boolean }>;
