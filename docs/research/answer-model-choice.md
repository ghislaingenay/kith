# OpenAI model and API choice for writing Answers

Research date: 2026-10-09. All pages were read on that date. Sources are primary: OpenAI developer docs (`developers.openai.com`, read through the `.md` versions of each page that the site publishes), the OpenAI API changelog, the OpenAI system card PDF on `cdn.openai.com`, and the official `openai` Python SDK (GitHub `openai/openai-python` and PyPI). Anything not confirmed on a fetched primary page is marked **unverified**.

Workload assumed throughout: one Ask = system prompt + 5 reranked Chunks (~500 tokens each) + Query ≈ **3,000 input tokens**, with an Answer of up to ~1,000-2,000 output tokens. The Answer must use only the passages, cite them with `[n]` markers, say "not found" otherwise, and reply in the Query's language (English and French at minimum). It is streamed to the browser over SSE, and the exact token count of each call is charged to the Tenant's token balance.

## 1. Summary and recommendation

**Default: `gpt-6-luna` with `reasoning.effort = "low"`, called through the Responses API (`AsyncOpenAI().responses.create(..., stream=True)`).**
**Stronger option: `gpt-6.1-sol` at `"low"` (its lowest effort). Cheaper or faster option: `gpt-6-luna` at `"none"`.**

Estimated cost per Ask at 3,000 input + 1,000 output tokens (Standard tier; output includes reasoning tokens):

| Model / effort | Input | Output | **Per Ask** | Per 1,000 Asks |
|---|---|---|---|---|
| `gpt-6-luna` (low or none) | 3,000 x $0.10/M = $0.0003 | 1,000 x $0.50/M = $0.0005 | **$0.0008** | $0.80 |
| `gpt-6.1-sol` (low) | 3,000 x $2/M = $0.006 | 1,000 x $10/M = $0.010 | **$0.016** | $16 |
| `gpt-6-astra` (low) | 3,000 x $10/M = $0.03 | 1,000 x $50/M = $0.05 | **$0.08** | $80 |

These numbers assume no prompt-cache write. With the default caching mode on GPT-5.6 and later models, the request writes its prefix to the cache. Those tokens are billed at 1.25x the input rate, so Luna would cost $0.000875 per Ask instead of $0.0008 (see 3.8). Set `prompt_cache_options={"mode": "explicit"}` to switch this off.

Reasoning against the criteria:

1. **Lineup.** As of 2026-10-09 OpenAI's three featured models are `gpt-6-astra` (flagship), `gpt-6.1-sol` (balanced) and `gpt-6-luna` ("for cost-sensitive, high-volume workloads") ([Models](https://developers.openai.com/api/docs/models)). All three are reasoning models with a 1,050,000-token context window and 128,000 max output tokens. The old "mini"/"nano" naming ended with GPT-5.4; Luna holds that slot now.
2. **Fit to the task.** A Kith Ask is a short, well-scoped, high-volume job: read 5 passages, answer, cite. OpenAI's model-selection guide maps "Luna · Low" to "Fine-grained edits, well-scoped problem-solving, and simple data extraction" and puts Sol and Astra on complex deliverables ([Model selection](https://developers.openai.com/api/docs/guides/model-selection)). The reasoning guide recommends `none` for "fast information retrieval, and classification" and `low` for "customer support / chat assistant workflows" ([Reasoning](https://developers.openai.com/api/docs/guides/reasoning)). Writing a grounded Answer with citations and a "not found" judgement is closer to `low`. Use `none` as the cheaper variant to A/B test, not as the default.
3. **Cost.** Luna is 20x cheaper than Sol per token and 100x cheaper than Astra. Luna at `low` costs under a tenth of a cent per Ask.
4. **API.** OpenAI says: "While Chat Completions remains supported, Responses is recommended for all new projects" ([Migrate to Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses)). The SDK README calls Responses "the primary API" and Chat Completions "the previous standard (supported indefinitely)" ([openai-python README](https://github.com/openai/openai-python/blob/main/README.md)).
5. **Token accounting.** In the Responses API, the final `usage` arrives on the terminal `response.completed` event as `event.response.usage`. Its fields are `input_tokens`, `input_tokens_details.cached_tokens`, `input_tokens_details.cache_write_tokens`, `output_tokens`, `output_tokens_details.reasoning_tokens` and `total_tokens`. Responses has no `include_usage` flag to set ([Responses create reference](https://developers.openai.com/api/reference/resources/responses/methods/create), [Responses streaming events](https://developers.openai.com/api/reference/resources/responses/streaming-events)).

Why not the others: `gpt-6.1-sol` cannot go below `low` effort (no `none`/`minimal`) and costs 20x more. Keep it as the quality fallback if Luna's French Answers or citation discipline fall short in the eval. `gpt-6-astra` costs 100x more and is pitched at agentic, multi-step work. `gpt-6-sol` costs the same as 6.1 Sol and its model page points to GPT-6.1 Sol as the newer Sol. `gpt-5.6-luna` costs 2x what `gpt-6-luna` costs, and the system card reports better factuality for GPT-6 Luna (see 3.9).

## 2. Comparison table

All figures read 2026-10-09. Prices are Standard tier, per 1M tokens, for prompts of at most 272K input tokens.

| Model id | Context / max output | Input | Cached input | Cache write | Output | Reasoning efforts (default) | `none` supported | Chat Completions | Build-tier limit | Est. cost per Ask (3k in / 1k out) |
|---|---|---|---|---|---|---|---|---|---|---|
| **`gpt-6-luna`** | 1,050,000 / 128,000 | $0.10 | $0.01 | $0.125 | $0.50 | none, low, medium, high, xhigh, max (medium) | yes | yes (function calling only at `none`) | 5,000 RPM, 2,000,000 TPM | **$0.0008** |
| `gpt-6.1-sol` | 1,050,000 / 128,000 | $2.00 | $0.10 | $2.50 | $10.00 | low, medium, high, xhigh, max (medium) | no (no `minimal` either) | yes, without tool calling | 5,000 RPM, 1,000,000 TPM | $0.016 |
| `gpt-6-astra` | 1,050,000 / 128,000 | $10.00 | $1.00 | $12.50 | $50.00 | low, medium, high, xhigh, max (default not stated on model page) | no (HTTP 400) | yes, tool calling requires Responses | 5,000 RPM, 1,000,000 TPM | $0.08 |
| `gpt-6-sol` (superseded by 6.1 Sol) | 1,050,000 / 128,000 | $2.00 | $0.20 | $2.50 | $10.00 | none ... max (medium) | yes | yes | (Sol row) 5,000 RPM, 1,000,000 TPM | $0.016 |
| `gpt-5.6-luna` (previous gen) | not read | $0.20 | $0.02 | $0.25 | $1.20 | not read | not read | not read | (Luna row) 5,000 RPM, 2,000,000 TPM | $0.0018 |

Sources: model pages [gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [gpt-6.1-sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [gpt-6-astra](https://developers.openai.com/api/docs/models/gpt-6-astra), [gpt-6-sol](https://developers.openai.com/api/docs/models/gpt-6-sol); [Pricing](https://developers.openai.com/api/docs/pricing); [Rate limits](https://developers.openai.com/api/docs/guides/rate-limits).

Batch and Flex are 50% of Standard. Fast mode is 2x Standard and Ultrafast (Sol and Astra only) is 6x. Prompts over 272K input tokens cost 2x input and 1.5x output, which never applies to a 3K-token Ask ([Pricing](https://developers.openai.com/api/docs/pricing)).

## 3. Details

### 3.1 Current lineup and model facts

- Models overview: "If you're not sure where to start, use GPT-6 Astra ... Choose GPT-6.1 Sol to balance intelligence and cost, or GPT-6 Luna for cost-sensitive, high-volume workloads." Also: "All latest OpenAI models support text and image input, text output, multilingual capabilities, and vision." Source: https://developers.openai.com/api/docs/models
- `gpt-6-luna`: "Our most efficient model for focused, high-volume tasks." Default snapshot `gpt-6-luna` and no dated snapshot listed. 1,050,000 context window, 922,000 max input tokens, 128,000 max output tokens, knowledge cutoff May 18, 2026, "Reasoning token support". "`reasoning.effort` supports `none`, `low`, `medium` (default), `high`, `xhigh`, and `max`." "Chat Completions supports function calling only with `reasoning_effort` set to `none`." Pricing: $0.1 input, $0.01 cached input, $0.125 cache writes, $0.5 output. Source: https://developers.openai.com/api/docs/models/gpt-6-luna
- `gpt-6.1-sol`: "Near-Astra performance for complex work at a lower cost." Same context and output limits, knowledge cutoff Apr 30, 2026. "`reasoning.effort` supports `low`, `medium` (default), `high`, `xhigh`, and `max`. The `none` and `minimal` reasoning efforts are not supported." "Chat Completions is supported without tool calling." Cached input is priced at 5% of input, not 10%. Source: https://developers.openai.com/api/docs/models/gpt-6.1-sol
- `gpt-6-astra`: "Our most capable model for the most demanding work." Same limits, knowledge cutoff Apr 30, 2026, efforts `low` to `max`. Source: https://developers.openai.com/api/docs/models/gpt-6-astra . Setting `none` on Astra "returns HTTP 400". Source: https://developers.openai.com/api/docs/guides/reasoning
- Release dates (changelog): GPT-6 Astra Sep 3, 2026; GPT-6 Sol and GPT-6 Luna Sep 22, 2026 ("These reasoning models accept text and image inputs and generate text through the Responses and Chat Completions APIs"); GPT-6.1 Sol Sep 29, 2026. Source: https://developers.openai.com/api/docs/changelog
- Unsupported parameters on reasoning models: "When reasoning effort is not `none`, remove `temperature`, `top_p`, and `top_logprobs`." Source: https://developers.openai.com/api/docs/guides/latest-model . So Kith cannot pin `temperature` at `low` effort.
- Also available: `text.verbosity` (`low` | `medium` default | `high`): "Lower values will result in more concise responses". Source: https://developers.openai.com/api/reference/resources/responses/methods/create

### 3.2 Reasoning tokens: billing, effort, reporting

- "While reasoning tokens are not visible via the API, they still occupy space in the model's context window and are billed as output tokens." Source: https://developers.openai.com/api/docs/guides/reasoning
- Set effort with `reasoning={"effort": "low"}` in Responses, or `reasoning_effort="low"` in Chat Completions. Supported values are model-dependent across `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. None of the GPT-6 models supports `minimal`: "If your existing request uses `minimal`, start with `low`". Sources: https://developers.openai.com/api/docs/guides/reasoning , https://developers.openai.com/api/docs/guides/latest-model
- Reported separately: yes. "The exact number of reasoning tokens used is visible in the usage object ... under `output_tokens_details`" (`reasoning_tokens`). Source: https://developers.openai.com/api/docs/guides/reasoning
- `output_tokens` may exceed visible text plus `reasoning_tokens`: "Some models, including GPT-5 models, generate tokens used to format or delimit response channels ... they aren't necessarily itemized separately in usage ... even when the reported `reasoning_tokens` value is `0`." Charge Tenants on `output_tokens`, not on a local count of the visible text. Source: https://developers.openai.com/api/docs/guides/token-counting
- Pre-flight input count: `client.responses.input_tokens.count(model=..., input=...)` "returns the exact count the model will receive", including formatting tokens. Use it if Kith wants to check a Tenant's balance before the call. Source: https://developers.openai.com/api/docs/guides/token-counting

### 3.3 Responses API vs Chat Completions

- "While Chat Completions remains supported, Responses is recommended for all new projects." Listed benefits include "Lower costs: ... improved cache utilization (40% to 80% improvement ...)" and better reasoning-model performance. "We recommend migrating all flows to the Responses API over time." Source: https://developers.openai.com/api/docs/guides/migrate-to-responses
- SDK README: "The primary API for interacting with OpenAI models is the Responses API" and "The previous standard (supported indefinitely) for generating text is the Chat Completions API." Source: https://github.com/openai/openai-python/blob/main/README.md
- Kith uses no tools, so Chat Completions would work with every candidate. Responses is still the better choice: OpenAI recommends it, `prompt_cache_options` is documented on it, and `usage` arrives without an extra flag.

### 3.4 Streaming text and getting final usage (Responses API, Python async)

Documented building blocks:

- Async client: "Simply import `AsyncOpenAI` instead of `OpenAI` and use `await` with each API call". For streaming, "The async client uses the exact same interface": `stream = await client.responses.create(..., stream=True)` then `async for event in stream`. Source: https://github.com/openai/openai-python/blob/main/README.md
- Event types to handle: "`response.created`, `response.output_text.delta`, `response.completed`, `error`". Source: https://developers.openai.com/api/docs/guides/streaming-responses
- `response.output_text.delta` (SDK class `ResponseTextDeltaEvent`) carries the text in `delta: str`. `response.completed` (`ResponseCompletedEvent`) carries the full `response`, including `response.usage`. Also handle `response.incomplete` (`ResponseIncompleteEvent`), `response.failed` (`ResponseFailedEvent`) and `error` (`ResponseErrorEvent`: `code`, `message`, `param`). Sources: https://developers.openai.com/api/reference/resources/responses/streaming-events ; SDK types `src/openai/types/responses/response_{text_delta,completed,incomplete,failed,error}_event.py` at https://github.com/openai/openai-python
- `usage` schema (`ResponseUsage`): `input_tokens`, `input_tokens_details.{cached_tokens, cache_write_tokens}`, `output_tokens`, `output_tokens_details.reasoning_tokens`, `total_tokens`. Sources: https://developers.openai.com/api/reference/resources/responses/methods/create ; https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_usage.py
- The only `stream_options` field in Responses is `include_obfuscation`. Responses has no `include_usage`. Source: https://developers.openai.com/api/reference/resources/responses/methods/create

Sketch for Kith's `OpenAIAnswerProvider`. The calls and field names come from the sources above. Combining them into this function, and choosing the parameter values, is this research's suggestion:

```python
from openai import AsyncOpenAI

client = AsyncOpenAI()  # reads OPENAI_API_KEY

stream = await client.responses.create(
    model="gpt-6-luna",                       # settings.ANSWER_MODEL
    reasoning={"effort": "low"},
    instructions=SYSTEM_PROMPT,               # "answer only from these passages, cite [n], else not found"
    input=passages_and_query,                 # str or list of message items
    max_output_tokens=8000,                   # caps reasoning + visible output (see 3.6)
    store=False,                              # default is True (stored >= 30 days)
    prompt_cache_options={"mode": "explicit"},  # no breakpoints => no cache write (see 3.8)
    stream=True,
)

usage = None
async for event in stream:
    if event.type == "response.output_text.delta":
        yield event.delta                     # forward to the browser SSE
    elif event.type in ("response.completed", "response.incomplete"):
        usage = event.response.usage          # may be None on incomplete (unverified, see 3.5)
        status = event.response.status        # "completed" | "incomplete"
        reason = event.response.incomplete_details and event.response.incomplete_details.reason
    elif event.type == "response.failed":
        error = event.response.error          # {code, message}; example shows usage null
    elif event.type == "error":
        ...                                   # event.code, event.message
# charge Tenant: usage.input_tokens + usage.output_tokens (output already includes reasoning)
```

For comparison, Chat Completions needs `stream_options={"include_usage": True}`. Usage then arrives on a last chunk with empty `choices`, with fields `prompt_tokens`, `completion_tokens`, `total_tokens`, `completion_tokens_details.reasoning_tokens`, `prompt_tokens_details.cached_tokens` and `prompt_tokens_details.cache_write_tokens`. Source: https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events

### 3.5 Streams cut off or erroring midway

- Chat Completions (documented): "If the stream is interrupted or cancelled, you may not receive the final usage chunk which contains the total token usage for the request." Source: https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events
- Responses, `max_output_tokens` hit: the response ends with `status: "incomplete"` and `incomplete_details.reason: "max_output_tokens"`, and "you could incur costs for input and reasoning tokens without receiving a visible response". So incomplete responses are billed. Source: https://developers.openai.com/api/docs/guides/reasoning
- Responses, `usage` on `response.incomplete` / `response.failed`: the `Response.usage` field is typed "optional ResponseUsage or null". The reference examples show `"usage": null` for both `response.incomplete` and `response.failed`. **Unverified** whether real incomplete events carry usage. Test it with a tiny `max_output_tokens` before relying on it. Source: https://developers.openai.com/api/reference/resources/responses/streaming-events
- Client disconnect (Kith's server drops the OpenAI stream, for example because the browser closed SSE): "To cancel a synchronous response, terminate the connection" ([Background mode](https://developers.openai.com/api/docs/guides/background)). **Unverified**: no fetched page says whether tokens generated before the disconnect are billed or how to learn their count. Assume they are billed and that Kith will not see `usage`. Recovery idea, **unverified**: create with `store=True` and later call `client.responses.retrieve(id)`. The other documented route to a resumable stream is `background=True, stream=True` with `starting_after=<sequence_number>`, but the docs warn it has a higher time to first token ([Background mode](https://developers.openai.com/api/docs/guides/background)).
- SDK behaviour: "When consuming a `Stream` or `AsyncStream`, read timeouts raise `APITimeoutError` and other HTTPX request failures raise `APIConnectionError` ... Stream consumption is not automatically retried, because replaying a request could duplicate output." Source: https://github.com/openai/openai-python/blob/main/README.md
- Practical consequence for the token balance: if no `usage` arrives, Kith must charge an estimate. One option is the pre-counted input (3.2) plus the `max_output_tokens` cap, or plus a count of the deltas already streamed. This is a design decision for Kith, not documented OpenAI behaviour.

### 3.6 Max output tokens and reasoning

- Responses parameter: `max_output_tokens`, "An upper bound for the number of tokens that can be generated for a response, including visible output tokens and reasoning tokens." Source: https://developers.openai.com/api/reference/resources/responses/methods/create . The Chat Completions equivalent is `max_completion_tokens`. Source: https://developers.openai.com/api/docs/guides/token-counting
- Can reasoning use the whole budget? Yes: "This might occur before any visible output tokens are produced, meaning you could incur costs for input and reasoning tokens without receiving a visible response." The documented handling checks `response.status == "incomplete" and response.incomplete_details.reason == "max_output_tokens"`, then checks whether `output_text` is empty ("Ran out of tokens during reasoning"). "OpenAI recommends reserving at least 25,000 tokens for reasoning and outputs when you start experimenting with these models." Source: https://developers.openai.com/api/docs/guides/reasoning
- Suggestion (not from the docs): at `low` effort with a 2,000-token Answer ceiling, start with `max_output_tokens` around 8,000. Log `reasoning_tokens` and the incomplete rate in the eval, then tighten or loosen the limit. On Luna even 25,000 output tokens costs at most $0.0125, so a generous cap is cheap.

### 3.7 Python SDK

- Latest `openai` on PyPI: **3.27.0**, uploaded 2026-10-09; `requires_python >=3.10`. Releases are frequent (3.23.0 on 2026-10-01 through 3.27.0 on 2026-10-09). Sources: https://pypi.org/project/openai/ (JSON at https://pypi.org/pypi/openai/json); `pyproject.toml` on `main` also says `version = "3.27.0"` and `requires-python = ">= 3.10"` (https://github.com/openai/openai-python/blob/main/pyproject.toml).
- The backend requires Python >=3.12, which satisfies this.
- Async client: `AsyncOpenAI`. The default transport is HTTPX2; `pip install openai[aiohttp]` with `http_client=DefaultAioHttpClient()` is optional "for improved concurrency performance". By default the SDK retries connection errors, 408, 409, 429 and >=500 twice (`max_retries`), and requests time out after 10 minutes (`timeout`). Source: https://github.com/openai/openai-python/blob/main/README.md
- `prompt_cache_options` is present in the SDK's `responses.py` on `main`. Source: https://github.com/openai/openai-python/blob/main/src/openai/resources/responses/responses.py

### 3.8 Prompt caching affects the exact token charge

- For GPT-5.6 and later (so all GPT-6 models), "cache writes cost 1.25× the standard, uncached input-token rate". Reads cost 0.1x (0.05x on GPT-6.1 Sol). The minimum cacheable prefix is 1,024 visible input tokens. Source: https://developers.openai.com/api/docs/guides/prompt-caching
- Default behaviour: "By default, OpenAI automatically chooses one implicit cache breakpoint", with `mode` defaulting to `implicit`. Implicit mode puts the breakpoint "at the end of the latest eligible message", and user messages are eligible. "With `explicit`, OpenAI does not create an implicit breakpoint ... If there are no explicit breakpoints, the request does not use prompt caching." Sources: https://developers.openai.com/api/reference/resources/responses/methods/create , https://developers.openai.com/api/docs/guides/prompt-caching
- Consequence for Kith (inference): each Ask's Chunks and Query differ, so under the default mode every ~3,000-token Ask would pay a 1.25x cache write that is unlikely ever to be read. Sending `prompt_cache_options={"mode": "explicit"}` with no breakpoints avoids that. If the system prompt alone ever reaches 1,024 tokens, put it in a developer-message `input_text` block with `prompt_cache_breakpoint` to get 0.1x reads. A top-level `instructions` string "cannot contain an explicit breakpoint".
- Usage reports the split. OpenAI's own cost formula: `ordinary_input = input_tokens - cached_tokens - cache_write_tokens`, cost = `ordinary + cached*0.1 + cache_write*1.25`, all at the input rate. Kith should store all three numbers per Ask if it ever bills Tenants in money rather than raw tokens. Source: https://developers.openai.com/api/docs/guides/prompt-caching

### 3.9 Multilingual / French quality

- The only primary statement found: "All latest OpenAI models support text and image input, text output, multilingual capabilities, and vision." Source: https://developers.openai.com/api/docs/models
- No language list, French-specific claim, or per-language benchmark (for example MMMLU) appears on the GPT-6 model pages, the GPT-6 guide, or the GPT-6 Sol/Luna October 2026 system card. The system card covers safety, health, hallucination, alignment and preparedness evals, and links to the list of languages ChatGPT supports. Source: https://cdn.openai.com/pdf/gpt-6-october.pdf
- Factuality: the system card says "GPT-6 Sol (October) and GPT-6 Luna (October) both deliver significant improvements in factuality over GPT-5.6 Sol (August) and GPT-5.6 Luna (August) across nearly all evaluation metrics." The card is about the ChatGPT deployment. It also says Codex and ChatGPT Work still run the earlier "September" versions. **Unverified** which version the API's `gpt-6-luna` alias serves. Source: https://cdn.openai.com/pdf/gpt-6-october.pdf
- The launch post (https://openai.com/index/introducing-gpt-6-sol-and-luna/) returned HTTP 403 to direct fetch. According to a search-engine excerpt only (**unverified by fetch**), it says Luna at higher effort "matches GPT-5.6 Sol at about a hundredth its cost".
- Bottom line: French quality is **unverified** from OpenAI sources. Kith's own EN/FR eval set is the only real evidence.

### 3.10 Citation marker format (relevant to `[n]`)

- OpenAI's citation guide recommends a specific marker format, `cite<source_id>`, "because they closely match the markers our models are trained on". It warns that "Custom or unfamiliar formats increase cognitive load on the model, leading to citation errors, especially in low reasoning effort". For injected context (Kith's case) it shows source IDs such as `block5` and rules like "Never invent new block IDs" and "Never cite outside knowledge". Source: https://developers.openai.com/api/docs/guides/citation-formatting
- Implication: if Luna at `low` makes `[n]` mistakes in the eval, try asking for OpenAI's marker format and rewriting it to `[n]` server-side before trying a bigger model or higher effort. This is optional and not needed for the MVP.

### 3.11 Rate limits at the lowest paid tier

- Tiers: Free (allowed geography, $100/month usage limit); **Build** ($5 total credit purchases, $500/month); Launch ($100, $5,000/month); Grow ($500, $200,000/month). The page now names three paid tiers. The "Tier 1" label used in `embedding-and-reranker-choice.md` no longer appears. Source: https://developers.openai.com/api/docs/guides/rate-limits
- Build tier Standard limits: Luna **5,000 RPM / 2,000,000 TPM**; Astra, Sol, Terra **5,000 RPM / 1,000,000 TPM**. The Luna and 6.1 Sol model pages show the same figures. Free-tier limits for these models are not published on the pages read. Sources: https://developers.openai.com/api/docs/guides/rate-limits , model pages above.
- At ~4,000-5,000 tokens per Ask, 2M TPM is roughly 400-500 Asks per minute on Luna. That is far above a small team's needs, so the binding constraint at Build tier is the $500/month usage limit.

## 4. Open questions

1. **Usage on `response.incomplete` and `response.failed`.** The schema allows it, but the reference examples show `null`. Check with a live call using `max_output_tokens=16` before the token-balance code depends on it.
2. **Billing and usage after a client disconnect** in a synchronous Responses stream are undocumented. Decide on a fallback charge, such as pre-counted input plus streamed or capped output. Optionally test whether `store=True` plus `responses.retrieve(id)` returns usage for a terminated response.
3. **French quality and `[n]` citation discipline of `gpt-6-luna` at `low` vs `none`** are unverified. Run the EN/FR eval on `gpt-6-luna`/`low`, `gpt-6-luna`/`none` and `gpt-6.1-sol`/`low`.
4. **Which `gpt-6-luna` version the API serves.** The system card separates "October" (ChatGPT) from "September" (Codex/Work) versions. The API model page lists only the alias `gpt-6-luna` and no dated snapshot, so behaviour may change under the same id. Re-run the eval when the changelog mentions Luna.
5. **Default `max_output_tokens`.** Set it from eval data (the observed `reasoning_tokens` distribution), not from the 8,000 suggestion above.
6. The SDK is releasing several versions a week (3.23 to 3.27 in nine days). Pin a range such as `openai>=3.27,<4` and watch the changelog.
