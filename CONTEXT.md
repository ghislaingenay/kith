# Kith

A small team (1 to 50 people) uploads documents into a shared pool and searches them, with an AI-written answer on top of the retrieved passages. Single tenant today, modelled so a second tenant is a data change.

## Language

### Tenancy and people

**Tenant**:
The organisation that owns a pool of documents. Every record belongs to exactly one Tenant.
_Avoid_: Workspace, team, organisation, account

**User**:
A person who can sign in, with Google or a magic link. Identified by email.
_Avoid_: Person, people, account

**Profile**:
The display information attached to a User (name, avatar). One per User.

**Tenant Membership**:
The link between a User and a Tenant, carrying that User's Role in the Tenant. It always links an existing User; before that User exists there is only a Pending Membership. A User may hold memberships in several Tenants.
_Avoid_: Member (as a noun on its own), seat

**Role**:
What a Tenant Membership is allowed to do within its Tenant. One of Owner, Admin, Member, Viewer.

**Owner** (Role):
The Role held by the User who created the Tenant. Exactly one per Tenant.
_Avoid_: Creator, superuser

**Admin** (Role):
The Role that manages Tenant Memberships and the Tenant's settings.

**Member** (Role):
The default Role for a newly added User. Can upload Documents and search.

**Viewer** (Role):
A Role that can search and read Documents but cannot upload or Ask.
_Avoid_: Guest, read-only user

**Grace Period**:
The 14 days between an Owner deleting a Tenant and its data being purged. During it the Tenant is invisible but the Owner can restore it.
_Avoid_: Retention window, soft-delete window

**Pending Membership**:
A Tenant Membership an Admin created for an email that has not signed in yet. It becomes active on that email's first sign-in, and is kept as history once accepted. There is no token; it can be activated for 7 days after it is created.
_Avoid_: Invitation, invite, allowlist, whitelist

### Authentication

**Session**:
The signed-in state a User's browser holds after authenticating: an opaque id in an httpOnly cookie, resolved server-side against Redis. Ends on logout, on the 30-day sliding expiry, or on revocation.
_Avoid_: Token (reserved for the Magic Link's one-time secret), login

**Magic Link**:
A single-use, time-limited link emailed to a User's address that signs them in without a password.
_Avoid_: Invite link (unrelated to Pending Membership), token

### Documents

**Document**:
A file uploaded into a Tenant by a User, who becomes its Uploader. PDF only in the first version.
_Avoid_: File, attachment

**Upload**:
One attempt by a User to move a PDF's bytes into a Tenant. A completed Upload produces exactly one Document; a rejected or abandoned Upload produces none. Not the same thing as the Document it may create.
_Avoid_: Document, file, transfer

**Uploader**:
The User who uploaded a Document. The Uploader, an Admin, or the Owner may delete it.
_Avoid_: Owner (that is a Role), author, creator

**Content Hash**:
A digest of a Document's bytes, used to detect that the same file was already uploaded into the Tenant.
_Avoid_: Fingerprint, checksum

**Ingestion**:
The background work that turns an uploaded Document into searchable Chunks. Its progress is the Document's Ingestion Status.
_Avoid_: Processing, indexing (indexing is one step of Ingestion)

**Ingestion Status**:
Where a Document is in Ingestion: `uploaded`, `processing`, `partial` (some Chunks made searchable, some failed), `ready`, `failed`, or `deleted`. Derived from the Chunks' indexing and embedding statuses once chunking is done. A Document can be searched by keyword before it is `ready`.
_Avoid_: State

**Ingestion Stage**:
The step of Ingestion a `processing` Document is currently in: `extracting`, `chunking`, `indexing` (Chunk text made keyword-searchable), or `embedding` (vectors added afterwards). Shown as the sub-label under the Ingestion Status. Separate from Ingestion Status, which stays a coarse outcome.
_Avoid_: Step, phase, progress (progress is pages extracted out of page count, not a Stage)

**Chunk Dead Letter**:
The record of a batch of Chunks that a Chunk-level Ingestion Stage (`indexing` or `embedding`) gave up on after its retries: which Tenant, Document and Stage, the Chunk ids, the last error and how many attempts were made. It is `open` until a replay re-does exactly those Chunks from the text kept in Postgres, then `resolved`.
_Avoid_: Dead Letter on its own, failed job, error log

**Page Text**:
The text extracted from one page of a Document, exactly as the PDF supplies it. Kept unchanged as the raw record of what extraction produced.
_Avoid_: Raw text, content

**Clean Text**:
A page's Page Text after cleanup: broken words rejoined across line breaks, soft-wrapped lines joined, paragraph breaks kept, whitespace and odd characters tidied, wording, case and accents untouched. Chunks are cut from it, and their positions refer to it.
_Avoid_: Normalized text, processed text

**Chunk**:
A passage of a Document's text, stored with its vector embedding, that search retrieves and answers cite. A Chunk knows which Document and which location in it (for PDF, the page) it came from. A Chunk never spans two pages.
_Avoid_: Passage, segment, fragment, snippet

### Search

**Query**:
The text a User submits to search. One Query produces one Search Result.
_Avoid_: Search term, prompt, question

**Filename Search**:
Narrowing the Document list by name. Returns Documents, not Chunks, each linking to its Document. It is not a Query: it is not logged and does not go through Retrieval.

**Retrieval**:
Finding the Chunks most relevant to a Query, by matching both its words and its meaning, merged into one ranking. Returns ranked Chunks with highlights and a link to their Document. Search and Ask use the same Retrieval.
_Avoid_: Semantic search, vector search, keyword search (these are mechanisms, not the concept)

**Search**:
A Query for which the User wants the retrieved Chunks only, with no Answer. Every Role can Search. Not counted in Usage.
_Avoid_: Semantic search, keyword search, normal search

**Answer**:
Text written by a language model from the retrieved Chunks in response to a Query, with Citations.
_Avoid_: Response, completion, RAG (RAG is the technique)

**Citation**:
A reference from an Answer to the Chunk that supports a claim.
_Avoid_: Source, reference

**Ask**:
A Query for which the User requested an Answer. Each Ask is kept as a record (its Query, User, Answer and cited Chunks) and is paid for from its Tenant's Credit Balance by an Ask Charge, whoever in the Tenant made it. An Ask stands alone: its Answer is written from its own Retrieval only, never from earlier Asks.
_Avoid_: Question, chat, prompt

**Rerank**:
Re-scoring the Chunks found by Retrieval for an Ask with a second, more precise model, and keeping only the best of them before they are cited. A Search is never reranked: it shows Retrieval's order. If Rerank cannot be done, the Ask goes on with Retrieval's order.
_Avoid_: Re-ranking, re-sorting, scoring (scoring is what Retrieval already does)

**Feedback**:
A thumbs-up or thumbs-down a User leaves on an Answer.
_Avoid_: Rating, vote

**Query Log**:
The record of a Query: who asked, what was retrieved, what was answered, and any Feedback.
_Avoid_: History, audit

**Audit Log**:
The record of who changed what in a Tenant: memberships added or removed, Roles changed, settings edited, Documents deleted, ownership transferred. Never contains Queries; those are the Query Log.
_Avoid_: Activity log, history, event log

### Limits

**Usage**:
What a Tenant has consumed: Documents, storage bytes, and the language-model tokens (input and output) spent writing Answers. Usage belongs to the Tenant, not to a User; each Ask still records which User spent it. The number of Asks is shown but does not limit anything; tokens are what an Ask is measured by, charged against the Credit Balance. Tokens spent embedding Chunks are not Usage; the Document and page Limits already bound them. Tokens spent on Rerank are not Usage either; the Ask they serve is already counted.
_Avoid_: Consumption, metering (metering is the act of recording Usage)

**Limit**:
A soft ceiling on one Usage dimension for a Tenant. Exceeding it warns; it does not bill. Asks have no Limit: the Credit Balance bounds them.
_Avoid_: Quota, plan, tier

**Credit**:
The unit a Credit Balance is shown in: 1,000 language-model tokens. Tokens are what is recorded; Credits are how they are shown and how top-ups are given. A typical Ask costs a few Credits.
_Avoid_: Token (on its own, to Users), point, coin

**Credit Balance**:
A Tenant's running balance of language-model tokens for Asks, shared by everyone in the Tenant. It starts with a grant when the Tenant is created, rises with Credit Adjustments and falls with Ask Charges; it never resets. An Ask may start only while it is above zero, so Asks running at once can leave it slightly negative. Seen by every Role that can Ask. Not money: nothing is billed.
_Avoid_: Credits (for the balance), quota, allowance, wallet

**Credit Ledger**:
Every change to a Tenant's Credit Balance, one row each, never edited: Ask Charges and Credit Adjustments. The Credit Balance is their sum.
_Avoid_: Usage log (top-ups are not Usage), transactions, billing history

**Ask Charge**:
The Credit Ledger row that takes an Ask's tokens, input and output as the language-model provider reported them, off its Tenant's Credit Balance. An Ask cut off part-way is charged what the provider reported; one the provider reported nothing for costs nothing, as does one whose Retrieval found no Chunks. Rerank and Query embedding tokens are never charged.
_Avoid_: Debit, cost, fee

**Credit Adjustment**:
A Credit Ledger row that adds to or takes from a Tenant's Credit Balance outside an Ask, always with a note saying why: the starting grant, a top-up, or the correction of a mistaken one.
_Avoid_: Top-up (one kind of Adjustment), refund, grant (the starting one is an Adjustment too)

### Quality

**Golden Set**:
A curated list of Queries with the Chunks that should be retrieved for each, used to measure Retrieval quality.
_Avoid_: Test set, benchmark, fixtures

**Seed Tenant**:
A Tenant populated with realistic Documents solely to run the Golden Set against.
_Avoid_: Test tenant, demo workspace
