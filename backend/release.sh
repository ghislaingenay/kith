#!/bin/sh
# The release step (ADR-0018): bring the schema to head, then create the
# search index if it is missing. Run in a one-off container from the new
# image before the new version starts; any failure exits non-zero so the
# deploy stops and the old version keeps serving.
set -eu

alembic upgrade head
python -m core.search.create_index
