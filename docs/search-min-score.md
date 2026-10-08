# Why weak passages show up in Search, and the minimum score

## What you see
Searching "Université" in a 3-page PDF returns all 3 pages, even though only page 3 is about university. Pages 1 and 2 (contact details, work experience) come back too, with no highlighted words.

## Why
Search is hybrid (#83). Two legs run, and their results are merged:

| Leg | Finds | Code |
|---|---|---|
| Keyword | passages containing most of the Query's words (the exact phrase ranks higher) | `keyword_leg` in `backend/app/core/search/opensearch_index.py` |
| Meaning | the `k` passages whose embedding is nearest to the Query's embedding | `meaning_leg` (a `knn` clause), same file |

The meaning leg is a nearest-neighbour search. It always returns its `k` closest passages, however weak the match. `k` is the result `size`, and **there is no minimum score** (no `min_score` or `max_distance` in the query). A 3-page document has 3 passages, so all 3 come back.

Passages found only by meaning have no `<mark>` highlight, because the highlight query uses the keyword words only. That is how to tell a keyword hit from a meaning-only hit in the UI.

## How the legs are merged
The `kith-rrf` search pipeline (`mapping.py`) uses Reciprocal Rank Fusion. It combines **ranks**, not scores. A passage ranked high by both legs wins. Raw similarity scores are ignored at this step.

## What a minimum score would do
A threshold on the meaning leg drops passages whose similarity is below it before the merge:
- Fewer weak, "nearest but unrelated" results. A Query with nothing relevant could return no results ("No passages match…").
- A threshold that is too high hides passages that are relevant but worded differently. That is the main benefit of searching by meaning.
- The keyword leg is unaffected. A passage containing the word still appears.
- Passages the cutoff removes no longer add to their rank in the merge. The remaining ranking is otherwise unchanged.

## Choosing a value
The index uses `cosinesimil` (`mapping.py`). OpenSearch converts cosine similarity to a score of `(1 + cosine) / 2`, so scores run from 0 to 1:
- 0.5 means cosine 0, which excludes almost nothing.
- Useful values are likely higher, perhaps 0.7 to 0.85. **This is an estimate**; it depends on the embedding model and the data and must be measured.

OpenSearch's k-NN query accepts `min_score` or `max_distance`; check which one applies to the `cosinesimil` space before using it.

## Status and next steps
Not implemented. Proposed:
1. Log each hit's raw meaning-leg score at debug level, to see real numbers for matching and non-matching Queries.
2. Add a `SEARCH_MIN_SCORE` setting to `SearchSettings` (`core/search/config.py`), unset by default so behaviour doesn't change.
3. Pass it to the `knn` clause, then tune: raise it while weak results still appear, lower it when good ones disappear.
