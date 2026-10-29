# Kith

A small team (1 to 50 people) uploads documents into a shared pool and searches them, with an AI-written answer on top of the retrieved passages. Single tenant today, modelled so a second tenant is a data change.

The domain language (Tenant, Document, Chunk, Ask, Credit, ...) is defined in [`CONTEXT.md`](CONTEXT.md). Design decisions are recorded as ADRs in [`docs/adr/`](docs/adr/).

## Stack

| Part | Tech |
| --- | --- |
| API | FastAPI, Python 3.12, uv, SQLAlchemy + Alembic |
| Background jobs | arq workers on Redis (ADR-0005) |
| Web app | Next.js 16, React 19, pnpm |
| Data | Postgres, Redis, OpenSearch (hybrid keyword + vector search) |
| Files | S3 (MinIO locally) |
| AI | Voyage (embeddings, rerank), OpenAI (answers) |
| Email | Mailpit locally, Resend in production |
| Production | Docker Compose on a VPS behind Caddy, images on GHCR, Sentry |

## Repo layout

```
backend/    FastAPI app, workers, Alembic migrations, scripts, tests
frontend/   Next.js app, unit (vitest) and e2e (Playwright) tests
infra/      docker-compose (dev and prod), Caddyfile, deploy and backup scripts
loadtest/   k6 smoke test run in CI
docs/       ADRs, research notes, quickstarts, design
```

## Getting started

Requirements: Docker with Compose, and `make`.

1. On WSL2 or Linux, raise the memory-map limit OpenSearch needs (details in [`docs/search-quickstart.md`](docs/search-quickstart.md)):

   ```sh
   sudo sysctl -w vm.max_map_count=262144
   ```

2. Create your local env file and add your own API keys:

   ```sh
   cp .env.example .env
   ```

3. Start everything, run the migrations and create the search index:

   ```sh
   make up
   make db-migrate
   make search-index-create
   ```

4. Open the app at http://localhost:3000 and sign in with a magic link. The email lands in Mailpit.

| Service | URL |
| --- | --- |
| Web app | http://localhost:3000 |
| API | http://localhost:8000 (health: `/health`) |
| Mailpit (magic-link emails) | http://localhost:8025 |
| Adminer (Postgres UI) | http://localhost:8080 |
| MinIO console | http://localhost:9001 |
| OpenSearch Dashboards | http://localhost:5601 |

## Environment variables

Local development only needs the variables in [`.env.example`](.env.example). Everything else has a working default in [`infra/docker-compose.yml`](infra/docker-compose.yml).

| Variable | Required | Purpose |
| --- | --- | --- |
| `VOYAGE_API_KEY` | For semantic search and ingestion | Embeddings and rerank. Without it, Search is keyword only and the ingest worker refuses to start. |
| `OPENAI_API_KEY` | For Ask | Writes Answers. Without it, every Ask answers 503. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | No | Override the local database credentials. |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `S3_BUCKET` | No | Override the local object storage credentials and bucket. |
| `NEXT_PUBLIC_ASK_SHOW_SOURCES`, `NEXT_PUBLIC_ASK_CITATION_MARKERS` | No | `false` hides an Answer's source cards or its `[n]` markers. |

The backend reads its other settings (upload limits, retrieval sizes, rerank, logging, ...) from `config.py` files under `backend/app/`, and each one has a default.

### Secrets

- `.env` is gitignored. Never commit it, and never paste real keys into docs, issues or code.
- The local defaults (`kithpassword`, `minioadmin`) are for your machine only. Production has no defaults: compose refuses to start until each secret is set.
- Production secrets live in `/opt/kith/.env` on the VPS. CI's deploy secrets (`VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_KNOWN_HOSTS`) live in GitHub Actions secrets. See [`docs/deploy-quickstart.md`](docs/deploy-quickstart.md).
- Variables prefixed `NEXT_PUBLIC_` are shipped to the browser. Never put a secret in one.

## Common commands

| Command | What it does |
| --- | --- |
| `make up` / `make down` | Start or stop the local stack |
| `make service-refresh service=<name>` | Rebuild and restart one service |
| `make db-migrate` / `make db-rollback` | Apply all migrations / undo the last one |
| `make db-revision msg="..."` | Autogenerate a new migration |
| `make search-index-create` | Create the OpenSearch index and search pipeline |
| `make rebuild-index` | Rebuild the search index from Postgres (ADR-0019) |
| `make embed-documents` | Queue embedding for Documents waiting on it |
| `make retrieve q="..." tenant=<slug> rerank=true` | Print what Retrieval returns for a Query |
| `make adjust-credits tenant_id=<uuid> credits=<n> note="..."` | Top up or correct a Tenant's Credits |

The full list, with usage notes, is in the [`Makefile`](Makefile).

## Tests

Backend, from `backend/`:

```sh
uv sync --all-groups
uv run pytest
```

Frontend, from `frontend/` (Node 22):

```sh
pnpm install
pnpm test          # vitest
pnpm test:e2e      # Playwright, against the running stack
pnpm lint
```

CI runs these in [`.github/workflows/`](.github/workflows/), plus a k6 smoke test (`smoke.yml`).

## Deploy

Every merge to `master` builds the images, pushes them to GHCR and deploys to the VPS. Migrations run as a release step (ADR-0018).

- First-time setup: [`docs/deploy-quickstart.md`](docs/deploy-quickstart.md)
- Day-to-day operations, backups and restores: [`docs/vps-operations.md`](docs/vps-operations.md)

## Contributing

- Issues and specs are tracked as GitHub issues.
- Read [`CONTEXT.md`](CONTEXT.md) for the domain language before naming things.
- Agent and skill setup is in [`AGENTS.md`](AGENTS.md).
