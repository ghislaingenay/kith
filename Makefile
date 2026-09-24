COMPOSE = docker compose -f infra/docker-compose.yml

# --rm to create a temporary container for running alembic commands
ALEMBIC = $(COMPOSE) run --rm app alembic

.PHONY: up down db-migrate db-rollback db-refresh db-revision db-history db-current

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
