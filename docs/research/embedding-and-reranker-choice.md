# Hosted embedding model and reranker choice for multilingual PDF RAG

Research date: 2026-09-14. All pages were read on that date unless noted. Sources are primary (vendor docs, vendor pricing pages, vendor blogs, OpenSearch docs) except where explicitly marked **(secondary)**.

Workload assumed throughout: ~80 PDFs, ~4,000 pages, ~3,000,000 tokens to embed once, plus a few hundred eval queries. For reranking the eval queries I assume 300 queries x 50 candidate chunks x ~400 tokens = ~6,000,000 rerank tokens (or 300 "searches" for per-search pricing).

## 1. Summary and recommendation

**Embedding: Voyage `voyage-4-large` (1024-dim default, cosine/dot-product), with `voyage-4` as the drop-in cheaper sibling in the same embedding space.**
**Reranker: Voyage `rerank-2.5` (GA, explicitly multilingual), with `rerank-3` (in preview, same API) as the upgrade to A/B test.**

Reasoning against the criteria, in order:

1. **Multilingual quality claims.** Voyage documents `voyage-4-large` as its top model "optimized for general-purpose and multilingual retrieval quality" ([Voyage embeddings docs](https://docs.voyageai.com/docs/embeddings)); Voyage's prior-generation launch post claims `voyage-3-large` outperforms OpenAI-v3-large and Cohere-v3 across multilingual evaluations ([Voyage blog, voyage-3-large](https://blog.voyageai.com/2025/01/07/voyage-3-large/)). Voyage does not publish a language count. Jina publishes the most explicit claim (119 languages for `jina-embeddings-v5-text-small`, [Jina news](https://jina.ai/news/jina-embeddings-v5-text-distilling-4b-quality-into-sub-1b-multilingual-embeddings/)) and Cohere states "over 100 languages" for its multilingual embed line ([Cohere embed docs](https://docs.cohere.com/docs/cohere-embed)). All three are credible; Voyage and Jina are the two strongest on paper. OpenAI only publishes MIRACL 54.9% and Mistral publishes no multilingual claim at all.
2. **1024-dim support.** Voyage v4 family: 1024 is the *default* output dimension ([Voyage API reference](https://docs.voyageai.com/reference/embeddings-api)). Jina v5-text-small: 1024 default. Cohere embed-v4.0: 1024 via Matryoshka (default 1536). OpenAI: 1024 via `dimensions` shortening (default 3072). Mistral: 1024 fixed.
3. **Cost within budget.** Every candidate embeds 3M tokens for under $0.40 list price; Voyage's first 200M tokens per model are free ([Voyage pricing](https://docs.voyageai.com/docs/pricing)), so ingestion and evaluation cost $0. Jina's 10M free tokens also cover this workload.
4. **Rate limits sane for a small worker.** Voyage Tier 1 (a payment method on file, no minimum spend): 3M TPM / 2,000 RPM for `voyage-4-large`, 8M TPM for `voyage-4` ([Voyage rate limits](https://docs.voyageai.com/docs/rate-limits)). Jina free keys: 100 RPM / 100K TPM (workable, ~30 min for 3M tokens). Cohere trial keys: 1,000 API calls/month and "cannot be used for production or commercial purposes". OpenAI Free: 100 RPM / 40K TPM. Mistral does not publish numbers.
5. **SDK maturity.** `voyageai` is an official PyPI package with `embed()` and `rerank()` in the same client ([Voyage docs](https://docs.voyageai.com/docs/embeddings)). Cohere (`cohere`) and OpenAI (`openai`) are equally mature. Jina's model page shows a `jina_client` snippet but I could not find that package on PyPI or GitHub (both 404), so treat Jina as REST-only from Python. Mistral has `mistralai`.

Why not the others, briefly: Cohere's public pricing page no longer shows per-token/per-search prices (only Model Vault hourly instances) and its trial key is non-commercial with a 1,000-calls/month cap. Jina is an excellent second choice on quality and cost but has the tightest free-tier TPM and no verified official Python SDK. OpenAI's multilingual score is the weakest documented and 1024 requires shortening. Mistral gives no multilingual or rate-limit documentation.

Reranker choice: `rerank-2.5` is the current GA Voyage reranker and is documented as "optimized for quality with instruction-following and multilingual support" ([Voyage reranker docs](https://docs.voyageai.com/docs/reranker)); `rerank-3` is "(In Preview)" with no multilingual wording yet. Cohere `rerank-v4.0-pro` is a strong alternative (32k context, "100+ languages") but the trial key allows only 10 req/min and per-search pricing is not on the public pricing page. Jina `jina-reranker-v3.5` (93 languages, 131k context) is the runner-up if you want a single vendor with Jina embeddings.

## 2. Comparison table

Prices are list prices as read on 2026-09-14. "Est. cost" = 3M embed tokens or ~6M rerank tokens / 300 searches.

### Embedding models

| Model id | Dims (1024?) | Max tokens/text | Multilingual claim | Price / 1M tokens | Free / entry rate limit | Python pkg | Est. cost (3M tok) |
|---|---|---|---|---|---|---|---|
| `voyage-4-large` | 1024 default; 256/512/2048 (Matryoshka) | 32,000 | "optimized for general-purpose and multilingual retrieval quality"; no language count | $0.12; first 200M free | Tier 1: 3M TPM, 2,000 RPM; 120K tokens/request | `voyageai` | $0.36 list, **$0 within free 200M** |
| `voyage-4` | 1024 default; 256/512/2048 | 32,000 | same wording | $0.06; first 200M free | Tier 1: 8M TPM, 2,000 RPM; 320K tokens/request | `voyageai` | $0.18 list, **$0** |
| `voyage-4-lite` | 1024 default; 256/512/2048 | 32,000 | same wording | $0.02; first 200M free | Tier 1: 16M TPM, 2,000 RPM; 1M tokens/request | `voyageai` | $0.06 list, **$0** |
| `text-embedding-3-large` | 3072 default; 1024 via `dimensions` shortening | 8,192 | MIRACL 54.9% (vs 31.4% ada-002); "English and non-English tasks" | $0.13 | Free tier: 100 RPM, 40K TPM; Tier 1 ($5 paid): 3,000 RPM, 1M TPM | `openai` | **$0.39** |
| `embed-v4.0` (Cohere) | 1536 default; 256/512/1024 (Matryoshka) | 128k context | "Multilingual"; the multilingual embed line "supports over 100 languages" (103 listed) | not on public pricing page; $0.12 **(secondary)** | Trial: 2,000 inputs/min, 1,000 API calls/month, non-commercial | `cohere` | **~$0.36 (secondary price)** |
| `embed-multilingual-v3.0` (Cohere) | 1024 fixed | 512 | "over 100 languages" (103 listed) | not on public pricing page | same as above | `cohere` | not computable from primary sources |
| `jina-embeddings-v5-text-small` | 1024 default; Matryoshka down to 32 | 32,768 | "119 languages" (v5 news); "93 languages" (model page) | $0.05 ($50 per 1B tokens) **(secondary)**; 10M free tokens per key | Free: 100 RPM, 100K TPM; Paid: 500 RPM, 2M TPM | none verified (REST) | $0.15 list, **$0 within 10M free** |
| `jina-embeddings-v4` | 2048 default; 128/256/512/1024/2048 | 32K | "29 languages (trained on 34)"; multimodal | same token pricing | same | none verified | $0.15 list, $0 |
| `jina-embeddings-v3` | 1024 default; 32-1024 | 8,192 | "89 languages" | same token pricing | same | none verified | $0.15 list, $0 |
| `mistral-embed` (`mistral-embed-2312`) | 1024 fixed | 8k | no vendor statement found | $0.10 | not published (Admin panel only) | `mistralai` | **$0.30** |

### Rerankers

| Model id | Max context | Multilingual claim | Price | Free / entry rate limit | Python pkg | Est. cost (300 queries) |
|---|---|---|---|---|---|---|
| `rerank-2.5` (Voyage) | 32,000 tokens; 1,000 docs & 600K total tokens per request | "multilingual support" | $0.05 / 1M tokens; no free tokens | Tier 1: 2M TPM, 2,000 RPM | `voyageai` | **~$0.30** (6M tokens) |
| `rerank-3` (Voyage, In Preview) | 32,000 tokens | not stated | $0.05 / 1M tokens; first 200M free | Tier 1: 2M TPM, 2,000 RPM | `voyageai` | $0.30 list, **$0** |
| `rerank-3-lite` (Voyage, In Preview) | 32,000 tokens | not stated | $0.02 / 1M tokens; first 200M free | Tier 1: 4M TPM | `voyageai` | $0.12 list, $0 |
| `rerank-v4.0-pro` (Cohere) | 32k | "100+ languages" | per search (1 query + up to 100 docs); price not on public page; ~$2 / 1K searches **(secondary, v3.5 figure)** | Trial: 10 req/min, 1,000 calls/month; Prod: 1,000 req/min | `cohere` | **~$0.60 (secondary)** |
| `rerank-v4.0-fast` (Cohere) | 32k | "100+ languages" | same basis | same | `cohere` | ~$0.60 (secondary) |
| `jina-reranker-v3.5` | 131,072 tokens (auto-truncate) | "93 languages" (trained on 24) | $0.05 / 1M tokens **(secondary)**; shares the 10M free tokens | Free: 100 RPM, 100K TPM | none verified (REST) | $0.30 list, **$0 within free** |

## 3. Per-candidate details

### 3.1 Voyage AI (voyage-4 family; voyage-3 family still listed)

- Current model ids and specs (read 2026-09-14): `voyage-4-large`, `voyage-4`, `voyage-4-lite`, `voyage-4-nano` (open-weight): 32,000-token context, output dimension 1024 (default), 256, 512, 2048. `voyage-4-large` is described as "optimized for general-purpose and multilingual retrieval quality", `voyage-4` as "general-purpose and multilingual". Source: https://docs.voyageai.com/docs/embeddings
- Older models still listed: `voyage-3-large`, `voyage-3.5`, `voyage-3.5-lite` (32K, 1024 default with 256/512/2048), `voyage-multilingual-2` (32K, 1024). Source: https://docs.voyageai.com/docs/embeddings
- API parameters: `input` list max 1,000 texts; `input_type` in {null, "query", "document"}; `truncation` default true; `output_dimension` 2048/1024(default)/512/256 for voyage-4-large, voyage-4, voyage-4-lite, voyage-3-large, voyage-3.5, voyage-3.5-lite, voyage-code-3; per-request token caps: voyage-4-lite 1M, voyage-4 320K, voyage-4-large 120K. Source: https://docs.voyageai.com/reference/embeddings-api
- Normalization / metric: "Voyage AI embeddings are normalized to length 1, which means that: Cosine similarity is equivalent to dot-product similarity, while the latter can be computed more quickly." Euclidean gives identical rankings. Source: https://docs.voyageai.com/docs/faq
- Pricing per 1M tokens: voyage-4-large $0.12, voyage-4 $0.06, voyage-4-lite $0.02, voyage-context-4 $0.12, voyage-multilingual-2 $0.12; "The first 200 million tokens ... are free for every account" on current models (200M for v4 family, 50M for older models). Source: https://docs.voyageai.com/docs/pricing
- Rate limits: Tier 1 requires adding a payment method (no minimum spend). voyage-4 8M TPM / 2,000 RPM; voyage-4-large 3M TPM / 2,000 RPM; voyage-4-lite 16M TPM / 2,000 RPM. Tier 2 (>= $100 paid) doubles, Tier 3 (>= $1,000) triples. Limits for accounts *without* a payment method are not stated. Source: https://docs.voyageai.com/docs/rate-limits
- Multilingual evidence beyond the docs wording: Voyage's voyage-3-large post claims it "outperforms OpenAI-v3-large and Cohere-v3-English by an average of 9.74% and 20.71%" across 100 datasets and is "general-purpose and multilingual" (blog, vendor primary): https://blog.voyageai.com/2025/01/07/voyage-3-large/ . The voyage-4 launch post focuses on the shared embedding space (mix and match models for query vs document) and MoE architecture and does not mention languages: https://blog.voyageai.com/2026/01/15/voyage-4/
- Python SDK: package `voyageai`. Snippet (from docs):
  ```python
  import voyageai
  vo = voyageai.Client()  # reads VOYAGE_API_KEY
  result = vo.embed(texts, model="voyage-4-large", input_type="document", output_dimension=1024)
  ```
  Source: https://docs.voyageai.com/docs/embeddings
- Estimated cost: 3M tokens x $0.12/M = $0.36 (voyage-4-large), $0.18 (voyage-4), $0.06 (voyage-4-lite); all $0 while inside the 200M free tokens.

### 3.2 Voyage rerankers

- Current: `rerank-3`, `rerank-3-lite` (both "(In Preview)"), `rerank-2.5`, `rerank-2.5-lite` -- all 32,000-token context. `rerank-2.5` description: "Our generalist reranker optimized for quality with instruction-following and multilingual support." `rerank-3`: "Highest accuracy. Recommendation for most applications." (no multilingual wording). Max 1,000 documents per request; 600K total tokens per request for the 2.x models. Source: https://docs.voyageai.com/docs/reranker
- Pricing per 1M tokens: rerank-3 $0.05 (200M free), rerank-3-lite $0.02 (200M free), rerank-2.5 $0.05 (no free tokens), rerank-2.5-lite $0.02 (no free tokens). Source: https://docs.voyageai.com/docs/pricing
- Rate limits Tier 1: rerank-3 / rerank-2.5 2M TPM, 2,000 RPM; lite variants 4M TPM. Source: https://docs.voyageai.com/docs/rate-limits
- Earlier multilingual evidence: rerank-2/2-lite launch post ("next generation of Voyage multilingual rerankers"): https://blog.voyageai.com/2024/09/30/rerank-2/ ; rerank-2.5 post includes multilingual evaluation sets: https://blog.voyageai.com/2025/08/11/rerank-2-5/
- Snippet:
  ```python
  reranking = vo.rerank(query, documents, model="rerank-2.5", top_k=10)
  scores = [(r.index, r.relevance_score) for r in reranking.results]
  ```
  Source: https://docs.voyageai.com/docs/reranker
- Estimated cost: ~6M rerank tokens x $0.05/M = $0.30 (rerank-2.5); $0 for rerank-3 within free tokens.

### 3.3 OpenAI text-embedding-3-large

- Max input 8,192 tokens; default 3,072 dimensions; `dimensions` parameter lets you "shorten embeddings ... without the embedding losing its concept-representing properties"; embeddings are "normalized to length 1", so cosine equals dot product. Source: https://developers.openai.com/api/docs/guides/embeddings
- Model page: "Most capable embedding model" for English and non-English tasks; price $0.13 / 1M tokens; rate limits Free 100 RPM / 40,000 TPM; Tier 1 3,000 RPM / 1,000,000 TPM; Tier 3 5,000,000 TPM. Source: https://developers.openai.com/api/docs/models/text-embedding-3-large
- Pricing page confirms $0.13 / 1M (3-large) and $0.02 / 1M (3-small); no batch price listed for embeddings. Source: https://developers.openai.com/api/docs/pricing
- Tier qualification: Free requires an allowed geography; Tier 1 = $5 paid. Source: https://developers.openai.com/api/docs/guides/rate-limits
- Multilingual claim: MIRACL average 54.9% (vs 31.4% for ada-002); MTEB 64.6%. Source: https://openai.com/index/new-embedding-models-and-api-updates/ (page returned HTTP 403 to direct fetch; figures taken from the search-engine excerpt of that same OpenAI page, so treat as primary-but-unverified-by-fetch).
- Python SDK: `openai`.
  ```python
  from openai import OpenAI
  emb = OpenAI().embeddings.create(model="text-embedding-3-large", input=texts, dimensions=1024).data
  ```
  Source: https://developers.openai.com/api/docs/guides/embeddings
- Estimated cost: 3M x $0.13/M = $0.39.

### 3.4 Cohere embed-v4.0 / embed-multilingual-v3.0

- Model table: `embed-v4.0` dimensions 256/512/1024/1536 (default 1536), 128k context, multilingual, text + images + mixed (PDF pages); `embed-multilingual-v3.0` 1024 dims, 512 context. Source: https://docs.cohere.com/docs/models
- Embed docs: "Our multilingual embed model supports over 100 languages, including Chinese, Spanish, and French." (stated for the multilingual v3 models; no separate count given for v4.0). Supported metrics: cosine, dot product, Euclidean. Source: https://docs.cohere.com/docs/cohere-embed ; language list (103 languages) at https://docs.cohere.com/docs/supported-languages
- API v2: max 96 texts per request; `output_dimension` 256/512/1024/1536 (embed-v4 and newer only); `input_type` search_document / search_query / classification / clustering / image; `truncate` NONE|START|END. Source: https://docs.cohere.com/reference/embed
- Pricing: the public page states embeddings "are priced based on the number of tokens embedded" and rerank "based on the quantity of searches" ("one query with up to 100 documents"; docs over 500 tokens split into chunks), but the page as read on 2026-09-14 shows only Model Vault hourly instance rates (Embed 4 $4.00-$5.00/hour; Rerank $5.00-$10.00/hour) and no per-token or per-search figure. Sources: https://cohere.com/pricing , https://docs.cohere.com/docs/how-does-cohere-pricing-work
  - **(secondary)** Third-party trackers list Embed 4 at $0.12 / 1M text tokens and Rerank 3.5 at $2.00 / 1K searches: https://www.aipricing.guru/cohere-pricing/ , https://pecollective.com/tools/cohere-pricing/
- Trial vs production keys: trial keys are free but "cannot be used for production or commercial purposes" and "are limited to 1,000 API calls a month"; Embed 2,000 inputs/min (trial and prod); Rerank 10 req/min trial, 1,000 req/min prod. Sources: https://cohere.com/pricing , https://docs.cohere.com/docs/rate-limits
- Python SDK: `cohere`.
  ```python
  import cohere; co = cohere.ClientV2()
  r = co.embed(model="embed-v4.0", input_type="search_document", embedding_types=["float"], texts=texts, output_dimension=1024)
  ```
  Source: https://docs.cohere.com/docs/cohere-embed
- Estimated cost: 3M x $0.12/M = $0.36 using the secondary price; ~85 API calls at 96 texts/call for ~8,000 chunks, so it fits the trial cap but the trial is non-commercial.

### 3.5 Cohere rerank-v4.0-pro / rerank-v4.0-fast / rerank-v3.5 / rerank-multilingual-v3.0

- Model table: `rerank-v4.0-pro` and `rerank-v4.0-fast` 32k context, "multilingual model that allows for re-ranking English and non-english documents"; `rerank-v3.5` and `rerank-multilingual-v3.0` 4k context. Source: https://docs.cohere.com/docs/models
- Rerank overview: all current models "100+ languages". Source: https://docs.cohere.com/docs/rerank-overview
- API: `max_tokens_per_doc` default 4096; "we recommend against sending more than 1,000 documents in a single request". Source: https://docs.cohere.com/reference/rerank
- Snippet: `co.rerank(model="rerank-v4.0-pro", query=q, documents=docs, top_n=10)`. Source: https://docs.cohere.com/docs/rerank-overview
- Pricing: per search unit (see 3.4); no public figure on 2026-09-14. **(secondary)** ~$2.00 / 1K searches (v3.5 figure). Estimated cost: 300 searches = ~$0.60.

### 3.6 Jina embeddings v5 / v4 / v3

- `jina-embeddings-v5-text-small`: 677M params, 1024 dims, Matryoshka truncation to 32/64/128/256/512/1024, 32K context, "93 languages (trained on 32)" on the model page, cosine similarity; "the default embedding model for Jina's API". Source: https://jina.ai/models/jina-embeddings-v5-text-small/
- v5 launch news (2026-02-19): small = 32,768 tokens, 1024 dims, "119 languages via Qwen3 tokenizer"; API curl example uses `"task": "retrieval.query"` and `"dimensions": 1024`. Source: https://jina.ai/news/jina-embeddings-v5-text-distilling-4b-quality-into-sub-1b-multilingual-embeddings/
- `jina-embeddings-v4`: 2048 default, Matryoshka 128/256/512/1024/2048, 32K tokens, "29 languages (trained on 34)", multimodal. Source: https://jina.ai/models/jina-embeddings-v4/
- `jina-embeddings-v3`: 1024 default, Matryoshka 32-1024, 8,192 tokens, "89 languages". Source: https://jina.ai/models/jina-embeddings-v3/
- Rate limits (per key): Free 100 RPM / 100K TPM; Paid 500 RPM / 2M TPM; Premium 5,000 RPM / 50M TPM; every new key gets 10M free tokens shared across all Jina APIs. Sources: https://jina.ai/embeddings/ , https://jina.ai/reranker/
- Pricing: jina.ai/pricing returns 404; the embeddings page only says pay-per-token with token packages. **(secondary)** $50 per 1B tokens ($0.05 / 1M) and $500 per 11B tokens: https://markaicode.com/pricing/jina-ai-pricing/ (search excerpt).
- Python SDK: the v4 model page shows `from jina_client import Client`, but https://pypi.org/project/jina-client/ , https://pypi.org/simple/jina-client/ and https://github.com/jina-ai/jina-client all returned 404 on 2026-09-14; the `jina` PyPI package is the unrelated orchestration framework. Treat as REST:
  ```python
  import httpx
  r = httpx.post("https://api.jina.ai/v1/embeddings", headers={"Authorization": f"Bearer {key}"}, json={"model": "jina-embeddings-v5-text-small", "task": "retrieval.passage", "dimensions": 1024, "input": texts})
  ```
- Estimated cost: 3M x $0.05/M = $0.15 list; $0 within the 10M free tokens. At 100K TPM the free key needs ~30 minutes for 3M tokens.

### 3.7 Jina reranker v3.5

- `jina-reranker-v3.5`: 0.6B params, multilingual listwise reranker, 131,072-token context with auto-truncation, drop-in replacement for `jina-reranker-v3`; model page: "trained on 24 languages, supports 93". Sources: https://jina.ai/reranker/ , https://jina.ai/models/jina-reranker-v3.5/
- Billing: token-based (query + documents), shared token pool with embeddings; same tier limits as above. Source: https://jina.ai/reranker/
- Estimated cost: ~6M tokens x $0.05/M (secondary price) = $0.30; $0 within free tokens.

### 3.8 Mistral embed

- `mistral-embed` (`mistral-embed-2312`, released 2023-12-11): 1024-dim vectors, 8k context, $0.1 / 1M tokens; the model card text describes it as "state-of-the-art semantic for extracting representation of code extracts" (sic). Sources: https://docs.mistral.ai/models/mistral-embed-23-12 , https://mistral.ai/pricing/api
- Embeddings guide: "Mistral AI embeddings are norm 1, cosine similarity, dot product or Euclidean distance are all equivalent"; retrieval can use the full 8192-token context. Source: https://docs.mistral.ai/studio/knowledge-rag/embeddings/text_embeddings
- API: `output_dimension` and `output_dtype` parameters exist "when available". Source: https://docs.mistral.ai/api/endpoint/embeddings
- Multilingual: no statement found on the model page, embeddings guide or overview.
- Rate limits: only visible in the Admin panel; not published. Sources: https://docs.mistral.ai/admin/user-management-finops/tier , https://help.mistral.ai/en/articles/698531-why-am-i-hitting-api-rate-limits-and-how-do-i-increase-them
- Python SDK: `mistralai`.
  ```python
  from mistralai import Mistral
  out = Mistral(api_key=key).embeddings.create(model="mistral-embed", inputs=texts)
  ```
- Estimated cost: 3M x $0.10/M = $0.30.

## 4. OpenSearch mapping for the recommended model

Voyage embeddings are unit-normalized, so cosine and inner product rank identically ([Voyage FAQ](https://docs.voyageai.com/docs/faq)). OpenSearch's `cosinesimil` space on the Faiss engine "automatically normalize[s] to unit length during indexing because Faiss uses inner product on normalized vectors internally", and the docs suggest `innerproduct` if vectors are already normalized ([knn spaces](https://docs.opensearch.org/latest/mappings/supported-field-types/knn-spaces/)). Use `cosinesimil` for a bounded score `(2 - d) / 2` in [0, 1], which is convenient for hybrid normalization; `innerproduct` is an equivalent option.

```json
PUT /documents
{
  "settings": { "index": { "knn": true } },
  "mappings": {
    "properties": {
      "text":      { "type": "text" },
      "embedding": {
        "type": "knn_vector",
        "dimension": 1024,
        "space_type": "cosinesimil",
        "method": {
          "name": "hnsw",
          "engine": "faiss",
          "parameters": { "ef_construction": 100, "m": 16 }
        }
      }
    }
  }
}
```

- `knn_vector` parameters: `dimension` (1-16,000), `space_type` (`l2` default; `cosinesimil`, `innerproduct`, ...), `method.name`/`engine`/`parameters`. Source: https://docs.opensearch.org/latest/mappings/supported-field-types/knn-vector/
- Engine/space support: Faiss supports `l2`, `innerproduct`, `hamming`, `cosinesimil`; Lucene `l2`, `cosinesimil`, `innerproduct`; NMSLIB is deprecated. HNSW defaults `m` 16, `ef_construction` 100, `ef_search` 100; Faiss is the default engine. Source: https://docs.opensearch.org/latest/mappings/supported-field-types/knn-methods-engines/
- Hybrid search: the `normalization-processor` (min_max / l2 / z_score normalization; arithmetic / geometric / harmonic mean combination) was **introduced in OpenSearch 2.10**. Source: https://docs.opensearch.org/latest/search-plugins/search-pipelines/normalization-processor/
- Reciprocal rank fusion: the `score-ranker-processor` with `technique: "rrf"` (`rank_constant` in [1, 10000], optional `weights`) was **introduced in OpenSearch 2.19**. Source: https://docs.opensearch.org/latest/search-plugins/search-pipelines/score-ranker-processor/

```json
PUT /_search/pipeline/rrf-pipeline
{
  "phase_results_processors": [
    { "score-ranker-processor": { "combination": { "technique": "rrf", "rank_constant": 60 } } }
  ]
}
```

## 5. Open questions

1. Voyage does not publish a language list or per-language benchmarks for the v4 family; the multilingual claim rests on the docs wording plus the voyage-3-large post. Run the project's own multilingual eval set against `voyage-4-large` and `jina-embeddings-v5-text-small` before locking in.
2. Voyage rate limits for accounts with no payment method are undocumented; add a card to get Tier 1 numbers (free tokens still apply).
3. `rerank-3` is in preview: check the reranker docs page again before shipping; if it gains a multilingual statement and GA status it replaces `rerank-2.5` at the same price with 200M free tokens.
4. Cohere's per-token and per-search prices are no longer on the public pricing page; if Cohere is reconsidered, get a quote or a production key to see billed rates.
5. Jina's official Python client could not be located on PyPI/GitHub; confirm whether `jina_client` exists or standardize on REST.
6. Mistral rate limits and language coverage are unpublished; excluded for that reason rather than quality.
7. Voyage's per-request cap for `voyage-4-large` is 120K tokens; the ingestion worker should batch by token count (not just 1,000 texts).
