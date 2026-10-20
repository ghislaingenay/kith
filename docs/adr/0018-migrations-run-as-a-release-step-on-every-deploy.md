---
status: accepted
date: 2026-10-20
---

# Migrations run as a release step on every deploy, and never break the running code

Every deploy runs a release step before the new version starts: a one-off container from the new `app` image runs `alembic upgrade head`, then `python -m core.search.create_index`. If either fails, the deploy stops and the old version keeps serving. The step runs on every deploy, not only when a migration is pending, because `alembic upgrade head` does nothing at head, so there is no "is a migration needed" check to get wrong. Running it by hand was rejected because it is easy to forget, and the API only warns when the schema is behind (`core/migrations.py`), so a forgotten migration would surface as errors on the first query that needs it.

## The rule that comes with it

Old code keeps serving while the release step runs and during the rollout, when the old and new `app` run side by side for about 30 seconds. So **a migration must work with the code that is already running**:

- Adding a table, or a nullable column or one with a default, ships in one deploy.
- Renaming or dropping a column, or making one `NOT NULL` without a default, is split in two: first a deploy that adds the new shape and stops using the old one, then a later deploy that removes it.

## Considered options

- **Migrate on app startup.** Rejected: every gunicorn worker and every replica would race to run it, and a failed migration would crash-loop the new container instead of leaving the old one serving.
- **A tool on the server that pulls new images by itself (Watchtower).** Rejected: it cannot run the migration before the new code starts.

## Consequences

- A rollback redeploys an older image and never downgrades the schema. That is safe only because of the rule above: the older code ran against this schema before the destructive half shipped.
- On AWS the same step becomes a one-off ECS task run before the service is updated.
