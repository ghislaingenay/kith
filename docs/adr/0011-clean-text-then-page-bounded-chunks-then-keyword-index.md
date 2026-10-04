---
status: accepted
date: 2026-10-01
amended: 2026-10-04
---

# Clean Text is stored per page, Chunks are page-bounded and cut from it, and keyword search is language-agnostic for Latin-script text

After extraction, each page's raw Page Text is cleaned into Clean Text (NFKC, control-character removal, hyphen and soft-wrap rejoining, whitespace collapsing; no header or footer removal, case and accents untouched) and stored in its own column beside the raw text. Chunks are cut from Clean Text one page at a time, about 500 tokens with 50 overlap, so a Chunk never spans two pages, and their character offsets point into the stored Clean Text. The Chunk text goes to Postgres first, then into the shared OpenSearch index under the same id, with the 1024-dimension vector field already in the mapping and left empty until the embedding phase.

Alternatives we rejected: cleaning at extraction (loses the raw text, and ADR-0010 keeps no history); cleaning after splitting, per Chunk (breaks token counts and offsets, and cannot repair a word hyphenated across a Chunk boundary); Chunks that span pages (a `page_start`/`page_end` schema, a stored joined text for offsets, and a cross-page highlight in the UI, for a Citation that is page-level in the MVP anyway); and a character-count or tiktoken-only size proxy for the embedding model, which waits for the embedding phase. Chunk size is measured with a general tokenizer (tiktoken `cl100k_base`) through LangChain's recursive splitter, which is close enough for a soft 500-token target (the research measured it 1.5 to 3.5% under Voyage's count on English and French samples). LangChain's own start indexes were wrong on 4 of 33 French Chunks in that research, so offsets are computed and verified by us, and a Chunk whose slice does not match is stored with unknown offsets and a warning.

Keyword search uses one analysis chain with no per-language fields: a character filter for curly quotes and dashes, the standard tokenizer, lowercase, and ASCII folding that keeps the original token. It is meant for Latin-script text (English, French, Spanish and similar), which behaves the same in any of them. We accepted losing stemming ("contrat" no longer matches "contrats" except through fuzziness) in exchange for not guessing a Document's language. Adding stemming later is a mapping change, so a new index and reindex under ADR-0012. Non-Latin scripts (Greek, Cyrillic, Chinese, Japanese, Korean, Arabic) are not supported by this chain and need their own decision.

Indexing is also separated from embedding. The Ingestion Stage order becomes `extracting`, `chunking`, `indexing`, `embedding`, and a Document is keyword-searchable once indexed, while staying `processing` at `embedding` until vectors exist, the same wait-state ADR-0010 used for chunking.

## Failure handling

A bulk indexing batch goes through the existing retry handler (three attempts, backoff) and an in-house circuit breaker (five consecutive failures open it for 30 seconds, then one probe), written without a library. A batch that still fails marks its Chunks `failed` in Postgres, writes a dead-letter row, and finishes the job without raising, so the queue's own retry does not multiply attempts on top. The Document is `partial` if some Chunks were indexed and `failed` if none were. A replay command re-indexes only the failed Chunks from the text stored in Postgres, never from the PDF. A failure outside the search store (storage or database unreachable) keeps ADR-0010's behaviour: back to `uploaded`, re-raise.

## Consequences

- `document_pages` gains a nullable Clean Text column; the `chunks` table gains separate indexing and embedding statuses with their own error columns (this extends ADR-0002, which listed only an embedding status). Ingestion Status is still derived from Chunk statuses, now from both.
- A Document records how its current Chunks were made in a `chunk_metadata` JSON column (size, overlap, cleaner version, tokenizer name, time), with no history. A retry replaces all of a Document's Chunks in one transaction. Changing the cleanup rules means bumping the cleaner version, then re-chunking the Documents whose stamp is older.
- Chunk token counts come from the general tokenizer, so the embedding phase recounts when it batches for Voyage, and may re-chunk if its tokenizer differs enough to matter. (Amended 2026-10-04: it does not re-chunk. A gap of a few percent on a soft 500-token target makes no difference to retrieval, so Voyage's counts are used only to batch requests under its 120K-tokens-per-request cap. See ADR-0014.)
- Header and footer removal is deliberately left out of the first cleaner version; the Golden Set decides whether it is added.
- Because the vector field is in the first mapping, adding embeddings later does not force a reindex of every Tenant.
- The "glossary" entries for Ingestion Stage and Ingestion Status, and the Clean Text and Page Text terms, are updated in `CONTEXT.md`.
