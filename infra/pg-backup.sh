#!/bin/sh
# Nightly Postgres backup (docs/deploy-quickstart.md, step 7). Dumps the
# database in pg_dump's custom format (compressed), uploads it to
# s3://$S3_BUCKET/backups/ under a timestamped name, and checks in to the
# Sentry Cron monitor on start, on success and on failure. S3's lifecycle
# rule deletes dumps after 14 days. Its env comes from the `pg-backup`
# service in docker-compose.prod.yml.
set -eu

# Sentry's check-in URL is built from the DSN
# (https://<key>@<host>/<project>) and the monitor's slug.
cron_url=
if [ -n "${SENTRY_DSN:-}" ]; then
  scheme=${SENTRY_DSN%%://*}
  dsn_without_scheme=${SENTRY_DSN#*://}
  public_key=${dsn_without_scheme%%@*}
  host_and_project=${dsn_without_scheme#*@}
  cron_url="${scheme}://${host_and_project%/*}/api/${host_and_project##*/}/cron/${SENTRY_CRON_MONITOR}/${public_key}/"
fi

# One request to the check-in URL. A Sentry outage must never fail the
# backup, so errors here are only printed.
check_in() {
  if [ -n "$cron_url" ]; then
    curl -fsS --max-time 10 --retry 3 -o /dev/null "${cron_url}?status=$1" \
      || echo "pg-backup: Sentry check-in '$1' failed" >&2
  fi
}

dump=/tmp/backup.dump

on_exit() {
  status=$?
  rm -f "$dump"
  if [ "$status" -ne 0 ]; then
    echo "pg-backup: failed" >&2
    check_in error
  fi
}
trap on_exit EXIT

check_in in_progress

s3_key="backups/${PGDATABASE}-$(date -u +%Y%m%dT%H%M%SZ).dump"

# Dump to a file first, so a failed dump never uploads a partial one.
pg_dump --format=custom --compress=6 --file="$dump"
aws s3 cp ${S3_ENDPOINT:+--endpoint-url "$S3_ENDPOINT"} --only-show-errors "$dump" "s3://${S3_BUCKET}/${s3_key}"

echo "pg-backup: uploaded s3://${S3_BUCKET}/${s3_key} ($(wc -c < "$dump") bytes)"
check_in ok
