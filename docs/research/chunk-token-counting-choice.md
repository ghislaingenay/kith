# Measuring chunk size for `voyage-4-large`: token counting options

Research date: 2026-09-29. All pages and registries read on that date. Sources are primary (Voyage docs, `voyageai` SDK source from the PyPI wheel, Hugging Face repo, PyPI metadata, `langchain-text-splitters` source) unless marked. Numbers labelled **(measured)** were produced by me on 2026-09-29 with a throwaway script (one English and one French Wikipedia text sample, ~85k and ~51k chars); they are **estimates** for our PDFs, not vendor claims.

Target: ~500-token chunks, 50 overlap, page-bounded, paragraph-boundary-preferring splits, English + French PDFs, embedding model Voyage `voyage-4-large` (ADR-0004, `docs/research/embedding-and-reranker-choice.md`).

## 1. Voyage's official token counting

- Voyage docs: tokenization "is automatically performed on our servers when you call the API"; token counting is offered via `voyageai.Client.count_tokens()` / `tokenize()`, and "Voyage's tokenizers are available on Hugging Face" (`AutoTokenizer.from_pretrained("voyageai/voyage-4-large")`). "To determine the exact number of tokens, please use the `count_tokens()` function." Source: https://docs.voyageai.com/docs/tokenization (read 2026-09-29).
- **`count_tokens` / `tokenize` run locally, they do not call the API.** SDK source (`voyageai` 0.5.0 wheel, `voyageai/_base.py`): `tokenizer(model)` does `tokenizers.Tokenizer.from_pretrained(f"voyageai/{model}")` then `no_truncation()`; `tokenize` = `encode_batch(texts)`; `count_tokens` = sum of `len()` of the encodings. The only network access is the one-time Hugging Face Hub download (cached). Source: https://pypi.org/project/voyageai/0.5.0/ (wheel read 2026-09-29). So there is no API rate limit, cost or latency for counting; the docs' rate-limits page has no token-counting endpoint (https://docs.voyageai.com/docs/rate-limits).
- **Tokenizer is published and loadable offline.** HF repo `voyageai/voyage-4-large` (public, not gated, Apache-2.0) contains `tokenizer.json`, `vocab.json`, `merges.txt`, `tokenizer_config.json`, `config.json`; tags show `qwen3` / `Qwen3ForCausalLM`, i.e. a Qwen3-family byte-level BPE. Source: https://huggingface.co/api/models/voyageai/voyage-4-large (read 2026-09-29). I downloaded `tokenizer.json` and loaded it with `tokenizers.Tokenizer.from_file(...)` with no other dependency (**measured**); post-processor is plain ByteLevel, so `encode()` adds no special tokens on this file. Whether the hosted API adds any special tokens per input (and therefore whether billed tokens exceed this count by a few) is **not documented** (unknown).
- The docs do not say all v4 models share one tokenizer. The SDK loads `voyageai/{model}` per model, and warns that "new models may use different tokenizers". The v4 sibling repos exist (e.g. `voyageai/voyage-4-lite` returned 200) but I did not diff them. Use the `voyage-4-large` file for `voyage-4-large`.
- `tokenizers` 0.23.2 (PyPI) depends only on `huggingface-hub`. https://pypi.org/project/tokenizers/

## 2. LangChain `langchain-text-splitters`

- Current version 1.1.2, released 2026-04-16; recent cadence 1.0.0 (2025-10-17), 1.1.0 (2025-12-14), 1.1.1 (2026-02-18), 1.1.2 (2026-04-16). Requires Python >=3.10, `langchain-core>=1.2.31,<2`. Source: https://pypi.org/project/langchain-text-splitters/ (read 2026-09-29). Actively maintained.
- **Footprint.** It hard-requires `langchain-core` 1.6.5, which requires `httpx`, `jsonpatch`, `langchain-protocol`, `langsmith`, `packaging`, `pydantic>=2.7.4,<3`, `pyyaml`, `tenacity`, `typing-extensions`, `uuid-utils` (https://pypi.org/project/langchain-core/). In a clean Python 3.13 venv the install pulled ~30 packages (**measured**). Pydantic constraint is only `>=2.7.4,<3`, so no clash with FastAPI's pydantic v2 in principle (a lock resolution against `backend/uv.lock` was not run). **Notable: `voyageai` 0.5.0 itself already depends on `langchain-text-splitters>=0.3.8`, `tokenizers>=0.14.0` and `pydantic>=2.7.4`** (PyPI metadata), so adding the Voyage SDK brings LangChain's splitter and its `langchain-core` chain in regardless. It also needs `numpy>=2.1.0` on 3.13, `pillow`, `aiohttp`, `requests`, `tenacity`, `aiolimiter`.
- **Length function.** `RecursiveCharacterTextSplitter(chunk_size, chunk_overlap, length_function=...)` accepts any `str -> int`, so `lambda s: len(tk.encode(s, add_special_tokens=False).ids)` with the Voyage tokenizer works directly (**measured**: 33 chunks from 40k chars of French, max 498 tokens with chunk_size=500, real Voyage tokens). Default separators `["\n\n", "\n", " ", ""]` give paragraph-preferring splits.
- Other constructors, from source (`base.py`, `sentence_transformers.py`, v1.1.2): `from_tiktoken_encoder` uses tiktoken (OpenAI vocab, not Voyage); `from_huggingface_tokenizer` requires a `transformers` `PreTrainedTokenizerBase` instance (raises otherwise), so a bare `tokenizers.Tokenizer` is not accepted, and it would add `transformers` as a dependency; `SentenceTransformersTokenTextSplitter` needs `sentence_transformers` and uses that model's tokenizer; `TokenTextSplitter` splits on tiktoken tokens and cuts mid-sentence (ignores paragraph boundaries). For Voyage, the useful path is the plain `length_function=` hook.
- **Offset preservation is NOT reliable (measured, and visible in source).** `add_start_index` is implemented in `TextSplitter.create_documents` as `index = text.find(chunk, max(0, index + previous_chunk_len - self._chunk_overlap))`, i.e. a forward search for the chunk text. Problems:
  1. `previous_chunk_len` is in characters but `_chunk_overlap` is in `length_function` units; with a token length function the offset is wrong, and can overshoot, so `find` returns **-1**.
  2. Chunks are re-joined from pieces with the separator, and whitespace-only/empty pieces are dropped and `strip_whitespace` trims, so a chunk's text is not always a verbatim substring of the source; `find` then returns -1 or a later duplicate.
  3. Repeated text can match an earlier/later duplicate.
  Test results (**measured**, chunk_size=500/overlap=50, real Voyage token counts, 40k chars French): 4 of 33 chunks had a `start_index` that did not point at the chunk text, and one was -1 (`find` returned -1); identical with `strip_whitespace` True or False. Synthetic repeated-paragraph and whitespace-heavy inputs each had 1 of 15 wrong.
  Consequence: if citations need character offsets into the page text, do not rely on `add_start_index`. Either compute offsets yourself (split into (start, end, text) spans first), or use LangChain only to produce the split points.
- Page-bounded: call the splitter once per page text (the splitter has no page concept); overlap then never crosses pages.

## 3. tiktoken as an approximation

No source states how far tiktoken is from Voyage tokens; treat as **unknown** from primary sources. My measurement against the real Voyage tokenizer (**measured, small sample, estimate only**):

| Text | chars/Voyage-token | cl100k_base / Voyage | o200k_base / Voyage | chars/5 / Voyage |
|---|---|---|---|---|
| English (85k chars) | 4.74 | 0.965 (undercounts ~3.5%) | 0.959 | 0.948 |
| French (51k chars) | 3.61 | 0.985 (undercounts ~1.5%) | 0.813 (undercounts ~19%) | 0.722 |

So `cl100k_base` happened to be within ~4% on both samples, `o200k_base` is unreliable on French, and a 5-chars-per-token rule undercounts French tokens by ~28%. tiktoken also adds a dependency and is not the model's tokenizer; since the exact tokenizer is free and offline, there is little reason to approximate.

## 4. Plain character-count proxy

Voyage documents one ratio: "The tokens produced by our tokenizer have an average of 5 characters, suggesting that you could roughly estimate the number of tokens by dividing the number of characters in the text string by 5" (https://docs.voyageai.com/docs/tokenization). It is stated for the tokenizer generally, with no per-language breakdown. My French sample gave 3.6 chars/token and English 4.7 (**measured**), so 5 is optimistic; for French, ~500 tokens is ~1,800 chars, not 2,500. A character proxy would make French chunks ~25-30% larger in tokens than intended if sized at 5 chars/token.

## 5. Limits that constrain chunk size

- `voyage-4-large`: 32,000-token context per input; up to 1,000 texts per request; 120K total tokens per request (https://docs.voyageai.com/docs/embeddings, https://docs.voyageai.com/reference/embeddings-api). `truncation` defaults to true (over-length inputs are truncated silently).
- Tier 1 rate limit for `voyage-4-large`: 3M TPM, 2,000 RPM (https://docs.voyageai.com/docs/rate-limits).
- Conclusion: a 500-token chunk is ~1.5% of the per-input context, so the model's limits do not constrain chunk size at all; the only limit that matters operationally is 120K tokens per request, i.e. ~240 chunks of 500 tokens per batch (batch by counted tokens, as ADR-0004 already says). The docs give no recommended chunk size.

## 6. Already in `backend/pyproject.toml` (read 2026-09-29)

Runtime deps: aiosmtplib, alembic, arq, asyncpg, boto3, dependency-injector, fastapi[standard], gunicorn, pypdfium2, pytest, redis, sqlalchemy[asyncio], structlog, uvicorn-worker. Dev: fpdf2, moto, pre-commit, pypdf, pytest-asyncio, pytest-cov, testcontainers. **Not present:** `voyageai`, `tokenizers`, `tiktoken`, `langchain-*`, `transformers`. (`fastapi[standard]` brings pydantic v2; `tokenizers` may already be absent from the lock.) `requires-python >=3.12`; `voyageai` 0.5.0 supports `<3.15,>=3.9`.

## 7. Recommendation

1. Count tokens with the published Voyage tokenizer through `tokenizers` (`Tokenizer.from_file` on a vendored/cached `voyageai/voyage-4-large` `tokenizer.json`, or the SDK's `count_tokens`, which is the same code path and also offline after the first Hub download). It is exact for the model, free, has no rate limit, and is the same mechanism Voyage documents.
2. For splitting, either (a) `RecursiveCharacterTextSplitter` with that `length_function`, one call per page, or (b) a small in-house recursive splitter. Prefer (b) or a wrapper that computes its own `(start, end)` spans if character offsets/citations matter, because `add_start_index` is unreliable with token-based lengths (section 2). If offsets are not needed and `voyageai` is being added anyway, (a) costs no extra dependency because `voyageai` already requires `langchain-text-splitters`.
3. Do not use character or tiktoken proxies except as a cheap pre-filter; the 5-chars/token figure is wrong for French by ~28% (measured).
4. Batch embedding requests by counted tokens (<120K per request).

## 8. Open uncertainties

- Whether the API adds special tokens per input beyond the local count (undocumented); leave headroom of a few tokens.
- Whether `voyage-4-large` and its v4 siblings share an identical tokenizer (not diffed); the ADR-0004 fallback to `voyage-4` should reload the tokenizer for the model in use.
- My chars/token and tiktoken ratios come from one English and one French Wikipedia sample, not our PDFs (PDF text has hyphenation, headers, tables); re-measure on real extracted text.
- Dependency resolution against the repo's actual `uv.lock` was not run; the pydantic-compatibility conclusion is from declared constraints only.
- `voyageai` 0.5.0 API surface for Python 3.13 was read from metadata/source, not exercised against the live API (no key used).
