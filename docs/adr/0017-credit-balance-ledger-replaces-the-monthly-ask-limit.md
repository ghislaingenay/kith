---
status: accepted
date: 2026-10-09
---

# Asks are bounded by a running Credit Balance kept as a ledger, not a monthly Ask Limit

Each Tenant has a Credit Balance of language-model tokens: a starting grant when onboarding creates the Tenant, Credit Adjustments from an operator script (`make adjust-credits`), and an Ask Charge per Ask for the input and output tokens the provider reported. It never resets. It is stored as an append-only Credit Ledger whose sum is the balance, and shown to Users in Credits (1 Credit = 1,000 tokens, rounded down). This replaces the MVP design's 30 Asks per calendar month, warned at 80 % and blocked at 100 %. Asks vary a lot in cost (reasoning tokens, longer Answers), so counting them hides what is spent; there is no billing, so a prepaid pool topped up by hand is the whole need. See `docs/research/ai-usage-allowance-ux.md` for how other products present this.

## Decisions

- **Tokens underneath, Credits on screen.** No product surveyed shows raw tokens to users, and GitHub Copilot, Cursor and Replit all moved away from counting requests because hard requests cost about 10x easy ones. Credits keep the fairness of tokens with a whole number people can read; the sidebar says "about 4 per Ask".
- **One pool per Tenant.** Usage already belongs to the Tenant (CONTEXT.md). Each Ask Charge still names its User.
- **An Ask may start while the balance is above 0.** Checking the worst case instead would block Users while plenty is left. Asks running at once can push the balance slightly negative; the rate limit (10 Asks per minute per User) bounds how far, and the next Ask is refused.
- **Charge what the provider reported.** An Ask cut off part-way is charged its reported tokens and the User is told why; one with nothing reported costs nothing, as does an Ask whose Retrieval found no Chunks (the model is not called). Google and Perplexity charge nothing for failures; we charge reported tokens because the provider bills them.
- **The ledger is append-only.** A mistaken top-up is fixed by a negative Credit Adjustment, and every Adjustment carries a note. An Ask Charge keeps its tokens if its Ask is later deleted, so deleting a User never changes a Tenant's balance.
- **No backfill.** Tenants that exist before this ships start at 0; the operator gives them Credits with the script. New Tenants get `STARTING_CREDIT_GRANT` (200 Credits) at onboarding.

## Considered options

- **One Ask = one credit.** The simplest to explain, rejected because Ask cost varies and a fixed unit hides it.
- **Monthly allowance that resets.** Rejected: it needs month-end logic and per-month top-ups for no gain without billing.
- **A percentage on its own.** Rejected: Copilot replaced exactly that because a percentage told users nothing about what an action costs.

## Consequences

- "Warn at 80 %" has no fixed total to measure against, so the sidebar turns amber below a fixed level (20 Credits by default) instead.
- The balance is a sum over the ledger. It is small per Tenant today; add a cached running total if the sum becomes slow.
- Admins cannot top up their own Tenant; the out-of-credits message tells Users to ask an Admin, who asks the operator.
