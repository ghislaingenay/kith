# Compose reads `.env` from the compose file's directory (infra/), so the
# repo-root `.env` (VOYAGE_API_KEY, ...) is passed explicitly when it exists.
COMPOSE = docker compose $(if $(wildcard .env),--env-file .env) -f infra/docker-compose.yml

# --rm to create a temporary container for running alembic commands
ALEMBIC = $(COMPOSE) run --rm app alembic

.PHONY: up down db-migrate db-rollback db-refresh db-revision db-history db-current search-index-create refresh-index clean-documents search-replay embed-documents retrieve adjust-credits

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

# usage: make service-refresh service=frontend
service-refresh:
	@if [ -z "$(service)" ]; then echo "usage: make service-refresh service=<name>"; exit 1; fi
	$(COMPOSE) up -d --build --force-recreate $(service)

# ── database ────────────────────────────────────────────────────────────────

db-migrate:
	$(ALEMBIC) upgrade head

db-rollback:
	$(ALEMBIC) downgrade -1

# drop all tables and re-run every migration from scratch
db-refresh:
	$(ALEMBIC) downgrade base && $(ALEMBIC) upgrade head

# usage: make db-revision msg="describe change"
db-revision:
	$(ALEMBIC) revision --autogenerate -m "$(msg)"

db-history:
	$(ALEMBIC) history --verbose

db-current:
	$(ALEMBIC) current

# ── search ──────────────────────────────────────────────────────────────────

# create the OpenSearch index, alias and RRF search pipeline (or update the pipeline); the API refuses to start without them
search-index-create:
	$(COMPOSE) run --rm app python -m core.search.create_index

# add fields newly in the mapping to the existing index, keeping its Chunks (development)
refresh-index:
	$(COMPOSE) run --rm app python -m core.search.refresh_index

# delete ALL Documents, Chunks, Uploads, their files in storage and the search index, then create the index again (development)
# usage: make clean-documents [yes=1]
clean-documents:
	$(COMPOSE) run --rm app python -m scripts.clean_documents $(if $(yes),--yes)

# usage: make search-replay [stage=indexing|embedding] [document=<uuid>] [limit=<n>]
search-replay:
	$(COMPOSE) run --rm app python -m scripts.replay_failed_batches $(if $(stage),--stage $(stage)) $(if $(document),--document-id $(document)) $(if $(limit),--limit $(limit))

# enqueue embedding for Documents waiting at the embedding stage or partial; the worker does the work
# usage: make embed-documents [document=<uuid>]
embed-documents:
	$(COMPOSE) run --rm app python -m scripts.embed_documents $(if $(document),--document-id $(document))

# print the Chunks Ask's Retrieval returns for a Query, with Rerank forced on or off (development)
# usage: make retrieve q="payment terms" tenant=<slug> rerank=true|false
retrieve:
	@if [ -z "$(q)" ] || [ -z "$(tenant)" ] || [ -z "$(rerank)" ]; then echo 'usage: make retrieve q="<query>" tenant=<slug> rerank=true|false'; exit 1; fi
	$(COMPOSE) run --rm app python -m scripts.retrieve "$(q)" --tenant "$(tenant)" --rerank "$(rerank)"

# ── credits ─────────────────────────────────────────────────────────────────

# give a Tenant Credits, or take back a mistaken top-up with a negative amount (ADR-0017)
# usage: make adjust-credits TENANT_ID=<uuid> CREDITS=<n> NOTE="why"
adjust-credits:
	@if [ -z "$(TENANT_ID)" ] || [ -z "$(CREDITS)" ] || [ -z "$(NOTE)" ]; then echo 'usage: make adjust-credits TENANT_ID=<uuid> CREDITS=<n> NOTE="<why>"'; exit 1; fi
	$(COMPOSE) run --rm app python -m scripts.adjust_credits --tenant-id "$(TENANT_ID)" --credits="$(CREDITS)" --note "$(NOTE)"
