# CODING_STANDARDS.md

## Python + FastAPI + Strict Domain-Driven Design

These rules are mandatory for all code generated, modified, or refactored by the AI agent.

## 1. Project Structure

Use `src/` as the application root.

Organize code by **business domain/module**, not by global technical layers.

Domain folders are **plural** when the domain name is a pluralizable noun
(`users/`, `orders/`) — this matches common FastAPI convention (e.g. the
widely-used [fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices)
guide), where resource-style domain folders are plural but every file inside
stays singular (`service.py`, not `services.py`). Domains named after a
capability rather than a resource (`upload/`, `dedup/`, `worker/`) stay
singular since there's nothing to pluralize — don't force a plural onto a
verb/capability name.

```text
project/
├── src/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── container.py
│   ├── exceptions.py
│   │
│   ├── users/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── models.py
│   │   ├── service.py
│   │   ├── repository.py
│   │   ├── dependencies.py
│   │   ├── exceptions.py
│   │   └── ...
│   │
│   ├── orders/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── models.py
│   │   ├── service.py
│   │   ├── repository.py
│   │   ├── dependencies.py
│   │   └── ...
│   │
│   └── core/
│       ├── retry/
│       ├── storage/
│       ├── pagination/
│       └── ...
│
├── tests/
│   ├── users/
│   └── orders/
└── alembic/
```

Each domain owns its code.

Do NOT create global:

```text
controllers/
services/
repositories/
models/
```

folders.

---

## 2. Domain Responsibilities

Each module should follow:

```text
router.py       → HTTP/API layer
schemas.py      → Pydantic API schemas
models.py       → database/ORM models
service.py      → business/domain logic
repository.py   → persistence access
dependencies.py → FastAPI dependencies
exceptions.py   → domain exceptions
```

Add files only when complexity requires them.

Business logic MUST stay inside the owning domain.

---

## 3. Strict DDD Rules

The domain must be independent from HTTP concerns.

Business logic MUST NOT:

- depend on `Request`/`Response`
- return HTTP-specific responses
- raise `HTTPException`
- contain FastAPI route logic
- directly instantiate infrastructure dependencies

Use domain-specific exceptions instead.

```python
class OrderNotFound(Exception):
    pass
```

FastAPI maps domain exceptions to HTTP responses at the API boundary.

---

## 4. Service Layer

`service.py` contains business rules and use-case orchestration.

Example:

```python
class OrderService:
    def __init__(
        self,
        repository: OrderRepository,
    ) -> None:
        self.repository = repository

    async def confirm(self, order_id: UUID) -> Order:
        order = await self.repository.get_by_id(order_id)

        if order is None:
            raise OrderNotFound()

        order.confirm()

        await self.repository.save(order)

        return order
```

Keep services focused.

Split `service.py` into multiple service modules when it becomes large.

Do not create an `application/` layer.

---

## 5. Repository

Repositories handle persistence only.

They MUST NOT contain business rules.

```text
service
   ↓
repository
   ↓
database
```

Use repository abstractions where they provide meaningful decoupling and testability.

Infrastructure/database details must not leak into business logic.

---

## 6. FastAPI Routes

Routes MUST be thin.

A route should:

```text
validate → inject dependencies → call service → return response
```

Example:

```python
@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    data: CreateOrderRequest,
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    return await service.create(data)
```

Do not put business logic inside routers.

Use:

- `response_model`
- correct HTTP methods
- correct status codes
- clear descriptions
- consistent REST resource naming

---

## 7. Pydantic

Use **Pydantic v2** for API boundaries.

Use `schemas.py` for:

- request models
- response models
- API validation
- serialization

Prefer Pydantic validation over manual validation.

Do not pass FastAPI request objects deep into business logic.

Use response models consistently.

---

## 8. Dependency Injection

Use:

### FastAPI `Depends`

For request-level dependencies:

- authentication
- authorization
- request validation
- database/session dependencies
- reusable endpoint dependencies

Dependencies can be chained and reused.

### `dependency-injector`

Use for application composition:

- services
- repositories
- database clients
- external clients
- storage implementations
- infrastructure services

`src/container.py` is the composition root.

Never instantiate infrastructure dependencies inside business logic.

### Adding a new dependency

`container.py` only holds **infrastructure singletons** — settings objects,
provider/client instances, the DB engine/session factory, the job queue.
Request-scoped objects (repositories, services) are _not_ registered in the
container; they're composed per-request in each domain's `dependencies.py`
via plain `Depends()` chains.

To wire in a new infrastructure dependency (e.g. a new external client):

1. Add a `Settings` class (Pydantic Settings) in the owning domain's
   `config.py`, following the existing `UploadSettings`/`DedupSettings`
   pattern.
2. Register it in `src/container.py`:
   - Settings: `providers.Singleton(MySettings)`.
   - The client/provider itself: `providers.Singleton(factory_fn, settings=my_settings)`,
     where `factory_fn` builds the concrete implementation from settings
     (see `StorageProviderFactory.create`, `create_job_queue`).
   - If the singleton should fail fast on bad config rather than on first
     use, add a comment noting it must be called eagerly during
     `lifespan`, matching `storage_provider`/`cache_provider`/`job_queue`.
3. Expose it to routes/services by adding a thin wrapper in the owning
   domain's `dependencies.py`:
   ```python
   def get_my_client() -> MyClient:
       return container.my_client()
   ```
   Do not call `container.x()` directly from a router or service — always
   go through a `dependencies.py` wrapper so infra stays swappable/mockable
   in tests via `Depends` overrides.
4. Consume it in a service/repository constructor via `Depends(get_my_client)`
   in the domain's own service/repository dependency function — never
   instantiate it directly inside business logic (see §3).
5. This project does not use `dependency_injector`'s `@inject`/`Provide[...]`
   wiring — stick to the `container.x()` + `Depends()` wrapper pattern
   already used throughout `dependencies.py` files for consistency.

---

## 9. Async

Use `async def` for non-blocking I/O:

- async database operations
- HTTP APIs
- Redis
- async file operations
- message brokers

Never use blocking I/O inside `async def`.

Examples of blocking operations:

```text
requests
time.sleep()
blocking file I/O
synchronous database drivers
```

If a synchronous library is unavoidable, run it in a threadpool rather than blocking the event loop.

Use normal `def` when synchronous execution is appropriate.

Do not make everything async automatically.

CPU-heavy work should run outside request processing, using an appropriate worker/task system.

---

## 10. Database

Use:

```text
SQLAlchemy 2.0
AsyncSession
Alembic
```

when applicable.

Use connection pooling.

Avoid:

- N+1 queries
- unbounded queries
- creating database connections per request
- blocking database calls
- exposing ORM models as API contracts

`models.py` contains persistence/ORM models.

`repository.py` handles database access.

`service.py` handles business behavior.

### Migrations

Use sequential, zero-padded revision IDs (`001`, `002`, `003`, ...) instead of
Alembic's default random hex IDs, for readability and to match migration
ordering to the numbering convention already used in technical designs (e.g.
`migrations/001_create_files_table.sql`).

```bash
PYTHONPATH=src alembic revision --rev-id 003 -m "add index to orders"
```

See `docs/database-migrations.md` for the full migration workflow (running
Postgres locally, applying/rolling back migrations, autogenerate caveats).

---

## 11. Errors

Use domain-specific exceptions.

```text
Domain error
     ↓
FastAPI exception handler
     ↓
HTTP response
```

Do NOT raise `HTTPException` from services or repositories.

Use guard clauses:

```python
if order is None:
    raise OrderNotFound()
```

Avoid deeply nested conditionals.

Handle unexpected errors centrally and never expose internal implementation details.

Repository and service layers must handle database errors, not ignore them.
For infrastructure-level failures (connection drops, constraint violations,
timeouts), catch and raise SQLAlchemy's own exception types
(`SQLAlchemyError`, `IntegrityError`, etc.) rather than inventing a custom
exception for them — domain-specific exceptions are reserved for business-
rule violations (not found, permission denied, invalid state), not
infrastructure failures.

---

## 12. Core Technical Systems

Do not create a business domain for reusable technical functionality.

Use `src/core/` for business-agnostic components:

```text
core/
├── retry/
├── storage/
├── pagination/
├── logging/
└── ...
```

Examples:

- retry/backoff
- file storage
- S3 clients
- caching
- pagination
- logging
- metrics
- tracing
- generic HTTP clients

If functionality contains business rules, it belongs to a domain.

---

## 13. Configuration & Lifecycle

Use Pydantic Settings for configuration.

Never hardcode:

- passwords
- API keys
- tokens
- database credentials
- secrets

Use FastAPI `lifespan` for shared resource initialization and cleanup:

- database engines
- Redis
- HTTP clients
- other application resources

Do not scatter startup/shutdown logic across modules.

---

## 14. Background Work

Do not make users wait for non-essential work.

Use FastAPI `BackgroundTasks` only for short, non-critical in-process work.

Examples:

```text
send lightweight notification
write non-critical log
```

Use a real task queue for:

- long-running work
- CPU-heavy work
- retries
- scheduling
- rate limiting
- critical jobs that must survive worker failure

---

## 15. API Documentation

Use FastAPI/OpenAPI as part of the API contract.

Define:

- `response_model`
- `status_code`
- descriptions
- summaries
- response documentation where useful

For private APIs, disable or restrict Swagger/OpenAPI documentation in production according to the project's security requirements.

---

## 16. Testing

Organize tests by domain:

```text
tests/
├── users/
├── orders/
└── ...
```

Prioritize:

```text
unit tests        → business logic
integration tests → database/external systems
API tests         → HTTP behavior
```

Most business rules should be tested without starting the complete application.

Use dependency injection to replace infrastructure during tests.

For API tests, use `httpx.AsyncClient(transport=ASGITransport(app=app))`, not
`fastapi.testclient.TestClient` — the latter triggers a
`StarletteDeprecationWarning` on import in this project's installed versions
(`httpx`+`starlette.testclient` compatibility is deprecated upstream).

Prefer fakes/stubs (e.g. a fake `AsyncSession` scripted with a fixed result)
for repository and adapter tests, and `unittest.mock.AsyncMock` when the
point of the test is asserting *how* a dependency was called rather than
round-trip behavior.

Extract a literal into a module-level, underscore-prefixed constant
(`_MAX_SMALL_FILE_SIZE`, `_LARGE_FILE_SIZE`) once the same value is repeated
across multiple test functions in a file — one clear source of truth for
"what does this test data represent" instead of the same magic number/string
retyped in each test, and a single place to update if the value needs to
change. The underscore signals it's private to that test module, matching the
convention already used for module-private helpers (`_read_bounded`,
`_generate_storage_key`) elsewhere in this codebase — not meant to be
imported by other test files. Keep the constant name descriptive of what the
value represents (`_OVERSIZED_MEDIATED_FILE_SIZE`, not `_SIZE_1`), so a
reader understands the test's intent without cross-referencing the FR/TD.
Don't extract a literal that appears only once, or that varies meaningfully
between the few tests using it — that's premature abstraction, not
deduplication.

---

## 17. Python Style

- Python 3.11+
- Type hints on all function signatures.
- Lowercase `snake_case` filenames.
- Names are descriptive: variables, functions, classes, attributes, files.
  A reader should know what a name holds or does without opening the code
  that fills it (PEP 8, Google Python Style Guide §3.16).
- Avoid abbreviations that are ambiguous or unfamiliar outside the project,
  and never shorten a word by deleting letters (`cnt`, `usr`).
- Descriptiveness grows with scope: `i` is fine in a 5-line block, too vague
  across nested scopes (Google Python Style Guide §3.16).
- Do not put the type in the name (`id_to_name_dict`); the name says what
  the value means, the annotation says what it is.
- Variables are nouns, functions are verbs (`upload_count`,
  `count_pending_uploads`); booleans read as a yes/no question.
- Never use `l`, `O`, `I` as single-character names (PEP 8).
- Prefer `is_active`, `has_permission`, `should_retry`, etc.
- Prefer functions when no state is required.
- Use classes when they provide meaningful state, identity, or dependency management.
- Prefer guard clauses and early returns.
- Avoid unnecessary abstractions.
- Avoid generic `utils.py`, `helpers.py`, or `manager.py` unless genuinely cohesive.
- Follow configured Ruff/formatter/type-checker rules.
- Use RORO when it improves clarity.
- Default to no comments. Only add one when the *why* is non-obvious — a
  hidden constraint, a subtle invariant, a workaround for a specific bug,
  behavior that would surprise a reader. If removing the comment wouldn't
  confuse a future reader, don't write it.
- Don't write comments that restate *what* the code does — descriptive
  names already do that. Keep any comment you do write short: one line,
  not a paragraph.

The agent chooses functional vs class-based style based on the situation.

---

## 18. REST Conventions

Use standard HTTP semantics:

```text
GET    /users
GET    /users/{user_id}
POST   /users
PUT    /users/{user_id}
PATCH  /users/{user_id}
DELETE /users/{user_id}
```

Use:

- plural nouns for collections
- lowercase URLs
- logical resource hierarchy
- consistent naming
- correct HTTP status codes

Introduce API versions such as `/v1` only when breaking compatibility requires it.

---

## 19. Agent Decision Rule

Before creating code, classify the responsibility:

```text
Business logic?
→ owning domain/service

HTTP/API?
→ router/schemas/dependencies

Persistence?
→ repository/models

Reusable technical capability?
→ core/

Configuration?
→ config.py

Dependency composition?
→ container.py
```

Before finishing a change:

```text
[ ] Correct domain owns the feature
[ ] No business logic in router
[ ] No business logic in repository
[ ] No HTTP dependency in business logic
[ ] Dependencies are injected
[ ] No blocking I/O inside async code
[ ] Pydantic used at API boundaries
[ ] Domain exceptions mapped at HTTP boundary
[ ] New business behavior is tested
[ ] No unnecessary abstraction introduced
```

**Primary rule: organize by business domain, keep business logic cohesive and framework-independent, and use dependency injection to isolate infrastructure.**
