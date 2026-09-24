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
Where a Document is in Ingestion: `uploaded`, `processing`, `partial` (some Chunks embedded, some failed), `ready`, `failed`, or `deleted`. Derived from the Chunks' embedding statuses once chunking is done.
_Avoid_: State

**Ingestion Stage**:
The step of Ingestion a `processing` Document is currently in: `extracting`, `chunking`, `embedding`, or `indexing`. Shown as the sub-label under the Ingestion Status. Separate from Ingestion Status, which stays a coarse outcome.
_Avoid_: Step, phase, progress (progress is pages extracted out of page count, not a Stage)

**Chunk**:
A passage of a Document's text, stored with its vector embedding, that search retrieves and answers cite. A Chunk knows which Document and which location in it (for PDF, the page) it came from.
_Avoid_: Passage, segment, fragment, snippet

### Search

**Query**:
The text a User submits to search. One Query produces one Search Result.
_Avoid_: Search term, prompt, question

**Filename Search**:
Matching a Query against Document names by keyword. Returns Documents, not Chunks.

**Retrieval**:
Finding the Chunks most relevant to a Query. Returns ranked Chunks with highlights and a link to their Document.
_Avoid_: Semantic search, vector search (these are mechanisms, not the concept)

**Answer**:
Text written by a language model from the retrieved Chunks in response to a Query, with Citations.
_Avoid_: Response, completion, RAG (RAG is the technique)

**Citation**:
A reference from an Answer to the Chunk that supports a claim.
_Avoid_: Source, reference

**Ask**:
A Query for which the User requested an Answer. Asks are counted in Usage.
_Avoid_: Question, chat, prompt

**Rerank**:
Re-scoring the Chunks found by Retrieval with a second, more precise model before they are shown or cited.

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
What a Tenant has consumed in a period: Documents, storage bytes, Asks, tokens.
_Avoid_: Consumption, metering (metering is the act of recording Usage)

**Limit**:
A soft ceiling on one Usage dimension for a Tenant. Exceeding it warns; it does not bill.
_Avoid_: Quota, plan, tier

### Quality

**Golden Set**:
A curated list of Queries with the Chunks that should be retrieved for each, used to measure Retrieval quality.
_Avoid_: Test set, benchmark, fixtures

**Seed Tenant**:
A Tenant populated with realistic Documents solely to run the Golden Set against.
_Avoid_: Test tenant, demo workspace
