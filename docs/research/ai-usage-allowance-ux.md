# How to show a Tenant's AI balance to users

Research date: 2026-10-09. All pages were read on that date. Sources are primary (vendor help centers, docs, pricing pages, official blogs and changelogs) except where marked **(secondary)**. Pages marked **(search excerpt)** returned HTTP 403 to direct fetch: the figures come from the search engine's excerpt of that same vendor page, so treat them as primary but not checked by fetch. Anything a vendor page did not say is marked "not stated"; no gap is filled from memory.

The question: Kith gives each Tenant a prepaid balance. It starts with a grant, an operator script tops it up, each Ask subtracts from it, and it never resets. It may dip slightly negative, and Asks are blocked at or below 0. The whole Tenant shares it, and everyone who can Ask sees it in the sidebar. What unit should it be shown and counted in? The candidates:

- (a) one Ask = one credit
- (b) raw tokens
- (c) credits derived from tokens or cost
- (d) a percentage remaining

## 1. Summary and recommendation

**Recommendation: (c). Record tokens underneath, show whole "credits" in the sidebar, and don't show a percentage on its own.**

What users see in the sidebar:

- A whole number with a thin bar under it, for example **"1,240 credits left"**. The bar runs from 0 to the balance right after the last top-up, so it fills back up on every top-up and never pretends to be a monthly allowance.
- Below a low-balance threshold, the bar turns amber and the line reads "Running low: ask an Admin to request a top-up".
- At or below 0, the Ask box is disabled with the line "Your team has used all its credits. Ask an Admin to request a top-up." Search keeps working.
- Each Answer may show "used N credits" after it. This is optional and can be deferred.

What the system records underneath:

- An append-only ledger in **tokens**: the grant, each top-up, and each Ask's input plus output tokens. This matches CONTEXT.md, which already says "tokens are what an Ask is measured by".
- A credit is a fixed display conversion, for example **1 credit = 1,000 tokens**. The sidebar shows the balance divided by that number and rounded down.
- With one Answer model there is no weighting. If a second model ever arrives, it gets a multiplier in the conversion, which is what GitHub, Notion, OpenAI and Microsoft do. The ledger itself does not change.
- An Ask that ends without an Answer is not subtracted. Its tokens can still be logged for the operator.

Why this and not the other candidates:

1. **"Credits" is the most common unit vendors show for a shared, top-up-able pool.** Eight of the 11 products surveyed show a vendor-named credit for their shared or purchasable balance:
   - Notion credits
   - Rovo credits
   - Microsoft Copilot Credits
   - Glean FlexCredits
   - ChatGPT Business credits
   - Perplexity credits
   - GitHub AI Credits
   - Replit credits

   Counted units ("prompts", "Pro Searches", "messages") and progress bars appear mainly for **per-user, time-window allowances that reset**, such as Gemini, Claude Team and the Notion AI allowance. Kith's balance is the first kind: shared, prepaid, topped up, never reset.
2. **Most vendors that started with per-request counting have moved to token- or cost-backed units, and give the same reason: requests vary too much in cost.**
   - GitHub replaced premium requests with token-metered AI Credits on 2026-06-01, saying the request model was "no longer sustainable".
   - Cursor dropped its 500-request cap because "the hardest requests cost an order of magnitude more than simple ones".
   - Replit dropped its flat $0.25 checkpoint for effort-based pricing.
   - OpenAI moved Enterprise chat from per-message rates to token rates "so that usage pricing is standardized across all product surfaces" (search excerpt).

   Kith already meters tokens, and the "may dip slightly negative" rule only makes sense if the cost is known after the Answer is written. So the record underneath should be tokens.
3. **Raw tokens (b) are not shown to end users by any surveyed product.** Vendors that bill on tokens convert them into a friendlier unit before users see it: GitHub uses "1 AI credit = $0.01 USD", OpenAI uses credits per 1M tokens, and Notion turns premium-model tokens into credits. Kith has no money involved, so a credit plays that role.
4. **A percentage alone (d) has no fixed base in Kith.** It also already failed at GitHub. In July 2026 GitHub changed its per-user view from a percentage of a budget to "450 / 1,000 AI credits used", because "that percentage gave them no view of their monthly usage". Kith's balance has no monthly allowance to be a percentage *of*: top-ups change the base. A bar is fine as decoration over a real number. A percentage is not fine as the only thing shown.
5. **One Ask = one credit (a) is the most predictable choice, but it hides cost differences and doesn't fit how Kith already meters.** Vendors that keep fixed per-action prices still tie them to model or tier:
   - Rovo charges basic interactions "10 Rovo credits" per billable event and premium ones a variable amount.
   - Microsoft charges 2 credits per generative answer and 10 for tenant-graph grounding.
   - ChatGPT Business charges 10 credits per GPT-6 message and 50 per Pro message (search excerpt).

   Kith's Ask is single-shot and does not carry earlier Asks forward, so its cost spread should be narrow. That keeps (c) predictable enough while staying honest. If testing shows the spread really is narrow, a later option is to show "about N Asks left" (balance divided by the recent average Ask). That is a deferred extra, not part of the first version.

The trade-off in one line: per-Ask counting is the easiest for users to predict, but unfair when Asks vary, and vendors kept abandoning it as agents made costs vary more. Token-backed credits are fair and match the meter, but users can't predict exactly what one Ask will cost. Kith's bounded, single-shot Ask keeps that uncertainty small.

## 2. Comparison table

"End-user unit" is what a non-admin member sees. "Pool" means a shared balance. "Window" means a per-user allowance that resets.

| Product | End-user unit | Per user or shared | Resets or pool/top-up | Near / at the limit | Failed or interrupted response | Unit changes |
|---|---|---|---|---|---|---|
| GitHub Copilot | **AI credits** ("450 / 1,000 AI credits used"); 1 credit = $0.01 | Per-user included credits, **pooled** at the billing entity for Business/Enterprise | Monthly included credits; budgets for extra | Budget alerts at 75/90/100%; included-usage alerts at 90/100%; banner offers "request more budget from your administrator" | Not stated | Premium requests (with model multipliers) became token-metered AI Credits on 2026-06-01: "no longer sustainable". In Jul 2026 the percentage view became a credit count |
| Cursor | Dollars of usage at API rates, in two pools; percentage in the editor **(secondary, forum)** | Per user (team pooling not stated) | Monthly, no rollover; on-demand after | Editor notification at the limit; dashboard "nearing usage limits" visibility | Not stated in docs; forum staff say aborted requests are charged **(secondary)** | Jun–Jul 2025: 500 requests/month became a $20 usage pool; Cursor publicly apologised and refunded |
| Replit | Replit credits; effort-based cost per checkpoint | Per account (team pooling not stated) | Monthly credits (Pro rolls over 2 months); budgets | Spending-threshold alerts; confirmation before a paid action | Not stated; a pricing-bug incident was refunded | Jun 2025: flat $0.25 per checkpoint became effort-based; Replit said the rollout "did not meet our standards" |
| Notion (AI allowance) | Usage view in Settings, unit not stated | Per member (wording "your usage") | Rolling 6-hour window plus monthly window | "Heads-up within Notion Agent chat as you get close"; pause, or "continue with Notion credits" if the admin allows it | Not stated | Not stated |
| Notion credits | **Credits** ($10 per 1,000) | **Shared across workspace** | Monthly (no rollover) or annual pool; buy more mid-cycle | Admins get alerts at 80% and 100%; agents pause when credits run out | Not stated (failed runs listed in Insights) | Not stated |
| Atlassian Rovo | **Rovo credits** (basic = 10 per event; premium variable) | Per-user allowances **combined into one shared pool** | Monthly, no rollover; extra usage or packs | Admins notified at 80% and 100% | Not stated | Repriced 2026-08-31; billing starts 2026-12-03 |
| Microsoft Copilot Chat / Studio agents | **Copilot Credits** (2 per generative answer, 10 per tenant-graph grounding) | **Tenant pool** (can be split by policy) | Monthly packs of 25,000; pay-as-you-go | Admin percentage notification; at 125% agents disabled; users see "This agent is currently unavailable. It has reached its usage limit." | Not stated | "Messages" became Copilot Credits on 2025-09-01, same rates **(search excerpt)** |
| Google Workspace Gemini | **Prompts** per window (e.g. "Up to 200 prompts / day"); per-feature counts | **Per user**, "aren't shared" | Daily and monthly resets; Gemini app windows | "Will notify you when you're close to your limit", then when it refreshes | Counts "if the prompt is successful and generates a response" | Limits "may change without notice" (capacity) |
| Glean | Basic queries unlimited; **FlexCredits** for agents and premium models | **"Pooled at the organizational level"** plus per-seat weekly allowance | Contract pool; admin monthly limits | Billable features pause at the limit; end-user copy not stated | Not stated | Agent-run rate card replaced |
| ChatGPT Business / Enterprise | Included per-seat usage, then **credits** (10 per message, set by model) **(search excerpt)** | Per seat included, then **shared workspace pool** | Credits valid 12 months; auto-reload | "Users see a banner when their included usage is exhausted"; when the pool is empty the feature is blocked and the member can request more **(search excerpt)** | Not stated | New Enterprise workspaces moved from per-message credits to token-based USD **(search excerpt)** |
| Claude Team | **Progress bars** for the 5-hour session and weekly limits | **Per member**, "rather than applied to the team as a whole" | 5-hour and weekly resets; optional usage credits after | Wait for the reset, or continue on usage credits | Not stated | Not stated |
| Perplexity Enterprise | **Pro Searches** per week; **credits** for premium features | Per seat allocation, then org pool **(search excerpt)** | Monthly credits | Balance shown; credits used per task under the ⋮ menu **(search excerpt)** | **Credits restored when a task fails "because of an error on our side"** **(search excerpt)** | Not stated |

## 3. Per-product details

### 3.1 GitHub Copilot

- Legacy model (now only for annual Pro/Pro+ plans): "A request is any interaction where you ask Copilot to do something for you". Pro gets 300 premium requests a month and Pro+ gets 1,500. "Each model has a premium request multiplier, based on its complexity and resource usage". Counters "reset on the 1st of each month at 00:00:00 UTC". Source: https://docs.github.com/en/copilot/concepts/billing/copilot-requests
- The change (blog, 2026-04-27, effective 2026-06-01): premium request units are replaced by GitHub AI Credits, calculated "based on token consumption, including input, output, and cached tokens" at each model's API rate. The stated reason is that "the current premium request model is no longer sustainable" because Copilot became agentic, and usage-based billing "better aligns pricing with actual usage". Included usage "can be pooled across an organization". Source: https://github.blog/news-insights/company-news/github-copilot-is-moving-to-usage-based-billing/
- "1 AI credit = $0.01 USD". "A user's included AI credits are pooled at the billing entity level". "A $0 USD user-level budget blocks the user immediately". Source: https://docs.github.com/en/copilot/concepts/billing-and-usage/organizations-and-enterprises/billing
- What users see: the Business/Enterprise usage card shows "450 / 1,000 AI credits used" (with a user budget) or "100 AI credits used" (without one). In the IDE, the Copilot icon in the status bar shows progress toward limits and the reset date. When credits run out, a banner offers "the option to request more budget from your administrator". Source: https://docs.github.com/en/copilot/how-tos/manage-and-track-spending/monitor-ai-usage
- Percentage to count (changelog, 2026-07-20): users can now "see how many AI credits they've used this billing cycle". Previously "the page showed usage only as a percentage of a budget", and "Many users don't have an individual budget, so that percentage gave them no view of their monthly usage". Source: https://github.blog/changelog/2026-07-20-copilot-users-can-now-see-ai-credits-used-per-billing-cycle/
- Alerts: budget alerts at 75%, 90% and 100%, in the GitHub UI and by email. A separate opt-in "Receive alerts when my included usage reaches 90% and 100%". Source: https://docs.github.com/en/billing/concepts/budgets-and-alerts (from search excerpt of that page)
- Failed requests: not stated on any GitHub page read.

### 3.2 Cursor

- Current docs: usage is priced per million tokens at each model's API rate, in two monthly pools ("Cursor Models" and "Other Models"), "visible in your editor settings and on your usage dashboard". "Requests are never downgraded in quality or speed". Docs also keep a "Legacy request-based pricing" section. Source: https://cursor.com/docs/account/pricing
- At the limit: "You'll see a notification in the editor". The user can enable on-demand usage or upgrade. "Unused usage does not roll over". Source: https://cursor.com/help/models-and-usage/usage-limits
- The change, part 1 (2025-06-16, edited 2025-06-30): "the Pro plan will move from request limits to compute limits; all users will get at least $20 of model inference at API prices per month". Source: https://cursor.com/blog/new-tier
- The change, part 2 (2025-07-04, "Clarifying our pricing"): the old model was 500 requests a month. "The hardest requests cost an order of magnitude more than simple ones". Calling included usage "rate limits" "wasn't an intuitive way to describe the limit". Cursor added "additional visibility on the Cursor Dashboard" for nearing limits and refunded unexpected charges from June 16 to July 4. Source: https://cursor.com/blog/june-2025-pricing
- **(secondary, forum)** In-editor percentage alerts at about 75% and 90%. Staff say aborted or stopped requests are charged because partial requests "could be used to get around limits". Sources: https://forum.cursor.com/t/aborted-errored-requests-are-being-charged/137676 , https://forum.cursor.com/t/you-are-projected-to-reach-your-usage-limits-by/122351 (not verified against official docs).

### 3.3 Replit

- Effort-based pricing launch (2025-06-18, updated 2025-07-02): "The original $0.25-per-checkpoint pricing was designed for the early version of Replit Agent". Simple changes typically cost under $0.25. Larger tasks are bundled into one checkpoint that may cost more. Source: https://replit.com/blog/effort-based-pricing
- Recap (2025-07-12): Agent v2 runs up to 20 minutes and could cost over $10, so one checkpoint per message no longer worked. The rollout "did not meet" Replit's standards. Larger checkpoints (e.g. $0.75 instead of three $0.25 ones) are "harder to interpret". A cost-calculation bug on July 11 was refunded, plus $10 credits for active users. Source: https://replit.com/blog/effort-based-pricing-recap
- Current docs: Agent work is "deducted from your Replit credits". Spending-threshold alerts and budgets are "hard caps to prevent unexpected charges". "Replit asks for confirmation before a paid action starts". Pro credits roll over two months. Source: https://docs.replit.com/billing/ai-billing

### 3.4 Notion

- AI usage allowance (Business/Enterprise): "Usage resets across a six-hour window", plus a monthly window that "resets all at once at the start of your billing cycle". Users get "a heads-up within Notion Agent chat as you get close". At the limit, features pause or, if the admin allows it, members "see the option to continue with Notion credits". Stated purpose: to keep Notion AI "fast and reliable" and run it "fairly for all users". The display unit is not stated. Source: https://www.notion.com/help/manage-your-usage-allowance-for-notion-ai
- Notion credits: "shared across your workspace". Monthly credits are "$10 per 1,000 credits" and "Reset each month. Unused credits don't carry over". Annual credits are "$13 per 1,000". What one credit measures is not stated. Source: https://www.notion.com/help/what-are-notion-credits
- Premium models spend credits at the provider's published token rates, with no markup (from search excerpt of https://www.notion.com/help/manage-ai-models-and-member-credit-spend).
- Credits dashboard: credits used, reset date, and "Current" vs "Estimated" usage chart. Admins get in-app and email alerts at 80% and 100%. Insights lists "failed runs", but billing for them is not stated. Source: https://www.notion.com/help/track-usage-in-the-notion-credits-dashboard
- Release note (2026-05-05): "If credits run out, all agents pause until you add more, so you won't get surprise bills". "Members can request a higher credit limit, but nothing goes through without admin approval". Source: https://www.notion.com/releases/2026-05-05

### 3.5 Atlassian Rovo

- "Rovo credits are Atlassian's unit of measurement for usage of AI capabilities". "All of your organization's Rovo credit allowances are combined into a single shared pool". Allowances reset monthly and "Unused credits do not roll over". Basic features cost "10 Rovo credits" per billable event. Premium features are variable. Rovo Search and summaries are free. Admins are notified at 80% and 100%. "Usage before August 31 uses the previous pricing". End-user on-screen copy and failed-interaction billing are not stated. Source: https://support.atlassian.com/rovo/docs/rovo-usage-limits/
- Blog (2026-09-01): allowance limits and billing take effect 2026-12-03. Rationale: "the value of software outgrows what seat count alone can capture". The model is framed around "predictability and control", with alerts before limits are reached. Source: https://www.atlassian.com/blog/company-news/expanded-usage-based-pricing
- Allowance figures (25 / 70 / 150 credits per user per month for Jira/Confluence Standard / Premium / Enterprise) are from the search excerpt of the support page and https://www.atlassian.com/licensing/rovo ; not re-checked by fetch.

### 3.6 Microsoft Copilot Chat and Copilot Studio agents

- "Copilot Credits are the unit that measures agent usage". Capacity is pooled "across the entire tenant". Rate card: classic answer 1, generative answer 2, agent action 5, tenant graph grounding 10. Licensed Microsoft 365 Copilot users are "No charge", subject to "fair usage limits". At 125% of prepaid capacity custom agents are disabled, and end users see "There is a billing issue." or "This agent is currently unavailable. It has reached its usage limit." Admins get email and admin-center notifications. Failed-response billing is not stated. Source (ms.date 2026-08-03): https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-messages-management
- Copilot Chat capacity packs: 25,000 credits per month per pack, replenished monthly. With a standalone pack, "When prepaid credits are exhausted, Copilot Chat is unavailable for those users until credits replenish". Admins can set a "Send notification when nearing capacity usage" percentage. Source (ms.date 2026-04-29): https://learn.microsoft.com/en-us/microsoft-365/copilot/pay-as-you-go/copilot-capacity-packs
- Unit change: "Starting on September 1, 2025, the common currency for agents changed from messages to Copilot Credits. There's no change in the quantity per prepaid pack or to the pay-as-you-go rate" **(search excerpt; exact Microsoft page not identified by fetch)**. No reason was stated in what I read.

### 3.7 Google Workspace with Gemini

- Workspace apps: "Limits apply to each user and aren't shared". Daily limits reset at 12 AM PT and monthly ones on the 1st. Units are per feature (e.g. slides per month, seconds per month). "If the prompt is successful and generates a response, it counts toward your monthly limit". Enforcement of Workspace Studio limits starts 2026-11-01. Page last updated 2026-10-07. Source: https://knowledge.workspace.google.com/admin/generative-ai/workspace-with-gemini/about-ai-usage-limits
- Gemini app for business accounts: Business/Enterprise editions get "Up to 25 prompts per 4 hours" (Pro) and "Up to 300 prompts / day" (Thinking). AI Expanded Access gets "Up to 200 prompts / day" (Pro). Gemini "will notify you when you're close to your limit", then tells you when it refreshes. Usage is under Settings > Usage Limits. "Limits may change without notice, including due to capacity constraints". The exact notification copy is not stated. Source: https://support.google.com/gemini/answer/14620100?hl=en&co=DASHER._Family%3DBusiness-Enterprise

### 3.8 Glean

- "FlexCredits are a measure of the complexity of the tasks Glean performs for each query, capability, or Agent run". "FlexCredits are shared and pooled at the organizational level". Fast Mode and basic search are unlimited. Each seat includes up to 100 Thinking/Adaptive Reasoning queries per week, and usage beyond that draws on the pool. Agent cost grows with connectors, steps, tools and model tier. End-user limit copy, admin alerts and failed-run billing are not stated. Page updated 2026-10-05. Source: https://docs.glean.com/glean-enterprise-flex-pricing
- Release notes: per-user monthly limits (Jul 2026), and department limits with an alert-only or block choice (Aug 2026). When a limit is hit, billable features pause (from search excerpts of https://docs.glean.com/release-notes/releases/2026-07-15-july-release and https://docs.glean.com/release-notes/releases/2026-08-12-august-release).

### 3.9 ChatGPT Business / Enterprise (all **search excerpt**: help.openai.com returned 403)

- Business: each seat has included usage, then "workspace credits can cover additional eligible usage". Credits are valid 12 months, with auto-reload. "If no credits are available in the workspace pool, the feature is blocked", and users can ask an owner to add more. Core models, search, file upload and canvas need no credits. Source: https://help.openai.com/en/articles/20001155-managing-credits-and-spend-controls-in-chatgpt-business
- Members' view: "Users see a banner when their included usage is exhausted". Owners get "email and in-product alerts when thresholds are hit". Source: https://help.openai.com/en/articles/11487671-flexible-pricing-for-the-enterprise-edu-and-business-plans
- Rate card: GPT-6 costs 10 credits per message and GPT-6 Pro 50. Deep research costs 50 per task. "Reasoning effort doesn't change the rate". Messages routed to a mini model cost 0. Agentic products are billed in credits per 1M tokens for "a direct mapping between model activity and credit consumption". Source: https://help.openai.com/en/articles/11481834-chatgpt-rate-card-business-enterpriseedu-credit-based-pricing
- Unit change: Enterprise token rates "replace ChatGPT message rates which were previously based on model and message count. Messages sent in chat will be based on token usage and model, so that usage pricing is standardized across all product surfaces". Source: https://help.openai.com/en/articles/20001415-chatgpt-rate-card-enterprise-token-based-pricing
- Failed-message billing: not found.

### 3.10 Claude Team

- "Usage limits on Team plans are per-member, rather than applied to the team as a whole". Standard seats get 1.25x Pro's per-session allowance and Premium seats 6.25x, with a weekly limit. Owners can enable usage credits so members keep working after their limit. Source: https://support.claude.com/en/articles/9266767-what-is-the-team-plan
- Display: Settings > Usage shows "progress bars showing how much of your five-hour session and weekly usage limits you've consumed". Usage depends on message length, attachment size, conversation length, tools, model and effort. Warning copy and failed-response treatment are not stated. Sources: https://support.claude.com/en/articles/9797557-usage-limit-best-practices , https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work

### 3.11 Perplexity Enterprise (all **search excerpt**: help-center pages returned 403)

- Plan table: Enterprise Pro gets "Extended limits (400/week)" Pro Searches, and Enterprise Max "Highest limits (4000/week)". Source: https://www.perplexity.ai/help-center/en/articles/11187416-which-perplexity-subscription-plan-is-right-for-you
- Enterprise Pro seats include 500 credits a month for premium features such as Computer. Standard searches and Ask don't need credits. The org pool is drawn on after a member uses their own allocation. Members see credits used per task under the ⋮ menu. Sources: https://www.perplexity.ai/help-center/en/articles/13901321-how-credits-work-for-enterprise-organizations-member-guide , https://www.perplexity.ai/help-center/en/articles/13901296-how-credits-work-for-enterprise-organizations-admin-guide
- Failed tasks: "If a Computer task can't finish because of an error on our side, Perplexity restores the credits used for that task", usually within minutes. A task that finishes with a result the user dislikes is not refunded. Source: https://www.perplexity.ai/help-center/en/articles/13838041-how-credits-work-on-perplexity

## 4. Patterns across products

1. **Two display families.**
   - Per-user allowances that reset are shown as counts ("prompts / day", "Pro Searches / week") or as progress bars (Claude, Notion allowance).
   - Shared pools you can buy into are shown as a **credit number**, with admins alerted at percentages (80/100% at Notion and Rovo, 75/90/100% at GitHub).

   No product in this survey uses a bare percentage as the end-user unit, and GitHub explicitly moved away from it.
2. **Requests and messages are moving to token-backed credits.** GitHub (2026), Cursor (2025), Replit (2025), Microsoft (2025, renaming only) and OpenAI Enterprise (2026) all moved this way. Every stated reason is that cost varies per request, mostly because of agents and long tasks. Fixed per-action prices survive where actions are bounded: Rovo basic, Microsoft generative answer, ChatGPT per-message by model.
3. **Moving from counts to cost-based units has hurt user trust when it was explained badly.** Cursor apologised and refunded. Replit said its rollout fell short and that bundled costs are "harder to interpret". The lesson is about communication and visibility, not about picking tokens.
4. **Running out usually blocks the paid feature, not the product.** Rovo Search, Glean Fast Mode and ChatGPT core models stay free. Notion agents pause. Users are pointed to an admin: GitHub "request more budget", Notion "request a higher credit limit", ChatGPT Business "request ... to add more credits".
5. **Failed responses are rarely documented.** Only Google ("if the prompt is successful and generates a response") and Perplexity (credits restored on errors on their side) say anything. Cursor's charging of aborted requests comes only from forum posts.

## 5. Open questions

1. Measure the real token spread of Kith Asks on the Seed Tenant before fixing the credit size. If 1,000 tokens makes a typical Ask cost an awkward number, change the conversion (it is display only).
2. The low-balance threshold: a fixed number of credits, or a share of the last top-up? Either works. The vendor precedent for admin alerts is 80% used.
3. Who sees the low-balance warning? Everyone who can Ask sees the balance, but only Admins can act on it (by contacting the operator). Vendor precedent: everyone sees the meter, and admins get the alerts.
4. Interrupted Asks (if Kith ever adds cancel): vendors split. Perplexity refunds its own errors, and Cursor charges aborts (secondary). Not needed until cancel exists.
5. OpenAI and Perplexity details rest on search excerpts (403 on fetch). Re-check them if either becomes a deciding precedent.
6. The Microsoft "messages to Copilot Credits" sentence was found only in a search excerpt. The exact source page was not confirmed by fetch.
