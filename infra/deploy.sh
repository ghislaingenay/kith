#!/bin/sh
# Deploys one image tag (docs/deploy-quickstart.md, step 8). Run from the
# directory holding docker-compose.prod.yml and .env: by the deploy workflow
# over SSH, by hand for the first start, and by the CI smoke test.
#   sh deploy.sh <image tag>
# It also starts a fresh server: the data services start before the release
# step, and `docker rollout` starts a service that is not running yet.
set -eu

# Shell env wins over .env, so the steps below use the new tag while .env
# still names the one that is serving.
IMAGE_TAG=${1:?usage: deploy.sh <image tag>}
case "$IMAGE_TAG" in
  *[!A-Za-z0-9_.-]*) echo "deploy: '$IMAGE_TAG' is not an image tag" >&2; exit 1 ;;
esac
export IMAGE_TAG

compose="docker compose -f docker-compose.prod.yml --env-file .env"

# Images are tagged with the commit SHA and never re-tagged, so one already on
# the server is the one CI pushed (CI's smoke test has nothing to pull).
$compose pull --policy missing

# Started if missing, never recreated: a changed data service in the compose
# file is applied by hand, so a deploy never restarts the database.
$compose up -d --no-recreate --wait postgres redis opensearch

# The release step (ADR-0018). If it fails, `set -e` stops here and the old
# containers keep serving.
$compose run --rm --no-deps app ./release.sh

# From here on the new tag is the serving one, also for a later `up -d`.
if grep -q '^IMAGE_TAG=' .env; then
  sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${IMAGE_TAG}/" .env
else
  echo "IMAGE_TAG=${IMAGE_TAG}" >> .env
fi

# Zero downtime: a second container starts, and the old one is removed once
# the new one is healthy. Caddy finds both through Docker DNS.
docker rollout -f docker-compose.prod.yml --env-file .env app
docker rollout -f docker-compose.prod.yml --env-file .env frontend

# The ingest worker takes no traffic, so a plain restart on the new image.
$compose up -d --no-deps worker-ingest

# Starts anything not running yet (Caddy on a fresh server) without touching
# the rest, then loads the Caddyfile the deploy just copied.
$compose up -d --no-recreate
$compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile

echo "deploy: ${IMAGE_TAG} is serving"
