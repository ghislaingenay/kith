---
status: accepted
date: 2026-10-09
---

# Answers are written by OpenAI `gpt-6-luna` behind a provider-agnostic `AnswerProvider`

Answers are written by OpenAI `gpt-6-luna` at reasoning effort `low`, through the Responses API, behind an `AnswerProvider` interface that a factory builds from settings (`ANSWER_PROVIDER`, `ANSWER_MODEL`, `ANSWER_REASONING_EFFORT`, `ANSWER_MAX_OUTPUT_TOKENS`). OpenAI because the team already holds credits there, not because of a quality comparison; the interface exists so a provider change is a new implementation plus an env change, never a change to Ask. Decided from `docs/research/answer-model-choice.md` (OpenAI pages read 2026-10-09). This replaces the MVP design's `{fast, quality}` model-tier table: there is one model, named by env.

## Decisions

- **`gpt-6-luna` at `low`.** About $0.0008 per Ask (3,000 input + 1,000 output tokens), 20x cheaper than `gpt-6.1-sol`. `low` rather than `none` because OpenAI warns that custom citation formats such as our `[n]` markers fail more often at low effort. `gpt-6.1-sol` at `low` is the fallback if English or French Answers or their markers fall short; it is one env change.
- **All five reranked Chunks go to the model.** Rerank already chose them (ADR-0015 amendment); the design's separate `ANSWER_CONTEXT_N=3` is dropped, so `RERANK_RESULT_LIMIT` is the one number.
- **`max_output_tokens` is 8,000, not the design's 1,024.** On these models the cap covers reasoning plus the visible Answer, and reasoning that fills it leaves an empty, still-billed reply. A larger cap costs nothing unless used; the prompt still asks for a short Answer.
- **OpenAI's default prompt caching is switched off** (`prompt_cache_options={"mode": "explicit"}`, no breakpoints). By default every request writes a cache entry billed at 1.25x the input rate, and an Ask's Chunks differ each time, so the write would almost never be read.
- **Token counts come from the provider.** The final usage on the stream's `response.completed` event is what an Ask Charge records (ADR-0017).

## Consequences

- French quality is undocumented for every OpenAI candidate; the Golden Set's French entries decide whether Luna stays, as they do for the Voyage models (ADR-0004).
- Luna has no dated snapshot, so the model behind the alias can change without notice. Pin a dated id if one appears.
- Whether a stream that errors or is cut off reports usage is not documented. When none is reported the Ask is charged nothing (ADR-0017), so the Credit Balance can slightly under-count what OpenAI billed.
