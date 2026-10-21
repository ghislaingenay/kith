# Deploy quickstart (VPS, first time)

How to bring Kith up on a fresh VPS behind Caddy, from an empty server to a signed-in first User. After this first run, every merge to `master` deploys by itself. Why it is shaped this way: ADR-0018 (migrations as a release step), ADR-0019 (OpenSearch is rebuilt, not backed up), ADR-0012 (OpenSearch security off on the VPS).

> **Not built yet.** This page describes the target setup. These pieces it relies on do not exist in the repo yet: `.github/workflows/deploy.yml` (until it lands, nothing pushes the images to GHCR) and the `pg-backup` service. Update this page as each one lands.

## The shape

```
internet ──443──▶ Caddy ──┬── /api/*, /health ──▶ app (FastAPI, gunicorn)
                          └── everything else ──▶ frontend (Next.js)

private Docker network: app, worker-ingest, frontend, postgres, redis, opensearch, pg-backup
outside services:       AWS S3 (files + backups), Resend (email), Sentry, OpenAI, Voyage
```

Only Caddy publishes ports (80, 443). Postgres and OpenSearch publish to the VPS's `127.0.0.1` only, for an SSH tunnel. Everything else publishes nothing.

## 1. What you need before starting

- A VPS: Ubuntu 24.04, **4 GB RAM minimum**, 2 vCPU, 40 GB disk. The stack uses about 2.7 GB, and a deploy briefly runs a second `app` and `frontend`.
- A domain you can add DNS records to. Below it is `app.example.com`.
- Accounts: AWS, Resend, Sentry, OpenAI, Voyage.
- Admin access to the GitHub repo.

## 2. Outside resources (one time, by hand)

**DNS.** An `A` record (and `AAAA` if the VPS has IPv6) for `app.example.com` pointing at the VPS. Caddy needs it in place before it can get the HTTPS certificate.

**AWS S3.** Use the region closest to the VPS.

1. Create a bucket, e.g. `kith-prod`, with "Block all public access" on. The app uses presigned URLs, so nothing in it is ever public.
2. CORS: the browser uploads PDFs straight to S3 and loads previews from it (ADR-0009).

   ```json
   [
     {
       "AllowedOrigins": ["https://app.example.com"],
       "AllowedMethods": ["GET", "PUT"],
       "AllowedHeaders": ["*"],
       "ExposeHeaders": ["ETag"],
       "MaxAgeSeconds": 3000
     }
   ]
   ```

3. Lifecycle rules:
   - prefix `pending/`: expire after 1 day. This is the backstop for abandoned uploads (ADR-0009).
   - prefix `backups/`: expire after 14 days.
4. An IAM user, e.g. `kith-vps`, with access keys. Give it a policy limited to this bucket: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket` on `arn:aws:s3:::kith-prod` and `arn:aws:s3:::kith-prod/*`.

**Resend.** Add and verify your sending domain (SPF and DKIM records in DNS), then create an API key with "sending access" only. Its SMTP login is host `smtp.resend.com`, port `465`, user `resend`, password = the API key.

**Sentry.** It receives errors and a sample of traces from the API, the ingest worker and the frontend, with no personal data.

1. Create three projects, `kith-api` (platform: FastAPI), `kith-worker` (platform: Python) and `kith-frontend` (Next.js), and note each DSN (project settings → Client Keys). For the products, tick Error monitoring and Tracing only: logs stay on the VPS.
2. Add an **Uptime** monitor on `https://app.example.com/health`.
3. Add a **Cron** monitor named `pg-backup`, scheduled daily, which the backup job checks in to.
4. Limit the `kith-frontend` DSN. It is public (every browser sees it), and it can only send events, not read them, so the risk is someone flooding the project with fake errors:
   - project settings → Security & Privacy → **Allowed Domains**: `app.example.com`, so browser events from other sites are rejected;
   - project settings → Client Keys → the key → **Rate Limiting**: for example 100 events per minute, so a flood can't use up the quota.

**GitHub** (repo settings → Secrets and variables → Actions).

- Variables, which get baked into the frontend image at build time:
  - `NEXT_PUBLIC_API_URL` = `https://app.example.com`
  - `NEXT_PUBLIC_ASK_SHOW_SOURCES` = `true`
  - `NEXT_PUBLIC_ASK_CITATION_MARKERS` = `true`
  - `NEXT_PUBLIC_SENTRY_DSN` = the `kith-frontend` DSN (leave it unset to turn Sentry off in the frontend). The browser can see it; a DSN only lets someone send events, not read them. The image reports as `production`, traces 10 % of page loads (never `/health`), and carries the release SHA.
  - `NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE` (optional) = the frontend's share of traces, 0 to 1. Leave it unset for `0.1`. `SENTRY_TRACES_SAMPLE_RATE` in the server's `.env` sets only the backend's.
- Secrets, used by the deploy job to reach the VPS:
  - `VPS_HOST`
  - `VPS_USER` (`deploy`)
  - `VPS_SSH_KEY` (the private half of a key made only for deploys)

## 3. Prepare the VPS

Run these as root, or with `sudo`, the first time.

```sh
# a user for deploys; you and CI log in as it
adduser --disabled-password deploy
mkdir -p /home/deploy/.ssh
# paste your own public key AND the CI deploy public key, one per line
nano /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh && chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys

# keys only, no root login
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/; s/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh

# firewall
ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw enable

# security updates install themselves
apt update && apt install -y unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades
```

Check you can still log in as `deploy` from a second terminal **before** closing the root session.

**Provider firewall.** In your hosting provider's control panel, add a firewall for the VPS that allows only inbound TCP 22, 80 and 443 (and UDP 443 for HTTP/3). It runs outside the server, so Docker cannot bypass it the way it bypasses `ufw` (see below): if a container ever publishes a port by mistake, this still blocks it.

**Docker.** Install Docker Engine and the compose plugin by following https://docs.docker.com/engine/install/ubuntu/, then:

```sh
usermod -aG docker deploy   # being in the docker group is the same as being root, so only this user gets it
```

> Docker bypasses `ufw` for published ports. A `ports: "5432:5432"` line would open Postgres to the internet whatever `ufw` says. That is why the prod compose file publishes only Caddy's ports, and binds Postgres and OpenSearch to `127.0.0.1`.

**Log rotation**, so container logs cannot fill the disk. In `/etc/docker/daemon.json`:

```json
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }
```

Then `systemctl restart docker`.

**OpenSearch memory maps.** OpenSearch will not start without this (same as in `docs/search-quickstart.md`):

```sh
echo 'vm.max_map_count=262144' > /etc/sysctl.d/99-opensearch.conf && sysctl --system
```

**The rollout plugin**, which deploys `app` and `frontend` without downtime. Run as `deploy`:

```sh
mkdir -p ~/.docker/cli-plugins
curl -fsSL https://raw.githubusercontent.com/wowu/docker-rollout/main/docker-rollout -o ~/.docker/cli-plugins/docker-rollout
chmod +x ~/.docker/cli-plugins/docker-rollout
docker rollout --help
```

**GHCR login**, needed only if the images are private. As `deploy`, with a GitHub personal access token that has `read:packages` only:

```sh
echo <token> | docker login ghcr.io -u <github-user> --password-stdin
```

## 4. Put the config on the VPS

Everything lives in `/opt/kith`, owned by `deploy`:

```sh
sudo mkdir -p /opt/kith && sudo chown deploy:deploy /opt/kith
```

The deploy job copies `docker-compose.prod.yml` and `Caddyfile` from the repo on every deploy, so the server always matches `master`. For the first run, copy them by hand (`scp infra/docker-compose.prod.yml infra/Caddyfile deploy@<vps>:/opt/kith/`).

The secrets go in `/opt/kith/.env`. Write it by hand, and never commit it.

```sh
touch /opt/kith/.env && chmod 600 /opt/kith/.env && nano /opt/kith/.env
```

```sh
# ── site ──
DOMAIN=app.example.com
# tag of ghcr.io/ghislaingenay/kith-backend and kith-frontend to run
IMAGE_TAG=<commit sha; the deploy job sets this on later deploys>

# ── postgres (password: openssl rand -hex 24) ──
POSTGRES_USER=kith
POSTGRES_PASSWORD=<random>
POSTGRES_DB=kith

# ── files: AWS S3 ──
STORAGE_PROVIDER=s3
S3_BUCKET=kith-prod
S3_REGION=<bucket region>
AWS_ACCESS_KEY_ID=<kith-vps key>
AWS_SECRET_ACCESS_KEY=<kith-vps secret>

# ── web ──
CORS_ALLOWED_ORIGINS=https://app.example.com
MAGIC_LINK_VERIFY_URL=https://app.example.com/verify
SESSION_COOKIE_SECURE=true
APP_URL=https://app.example.com

# ── email: Resend over SMTP ──
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USERNAME=resend
SMTP_PASSWORD=<resend api key>
SMTP_USE_TLS=true
MAIL_FROM_ADDRESS=noreply@example.com

# ── AI ──
OPENAI_API_KEY=<key>
VOYAGE_API_KEY=<key>

# ── observability ──
LOG_FORMAT=json
LOG_LEVEL=INFO
# Sentry: one project each for the API and the ingest worker; leave a DSN
# empty to turn it off for that service. The compose file sets
# SENTRY_ENVIRONMENT=production, and the image carries the release SHA.
SENTRY_API_DSN=<kith-api dsn>
SENTRY_WORKER_DSN=<kith-worker dsn>
# share of requests and jobs traced (0 to 1; /health is never traced)
SENTRY_TRACES_SAMPLE_RATE=0.1
```

The compose file reads this file twice: it fills in `${...}` values in `docker-compose.prod.yml` (missing ones stop it from starting), and it hands the whole file to `app` and `worker-ingest` as their settings. The other services get only what they need. The internal addresses (`DATABASE_URL`, built from the `POSTGRES_*` values, `REDIS_URL`, `SEARCH_URL`, the frontend's `BACKEND_URL`) are set in the compose file, so they are not in `.env`.

The other settings (upload caps, retrieval sizes, `STARTING_CREDIT_GRANT`, ...) have working defaults. Add one here only to change it. Tuning knobs with defaults: `GUNICORN_WORKERS` (2), `GUNICORN_GRACEFUL_TIMEOUT` (30 seconds, how long an Ask stream gets to finish on a deploy), `OPENSEARCH_HEAP` (`512m`).

## 5. First start

As `deploy` in `/opt/kith`. From here on `dc` means `docker compose -f docker-compose.prod.yml --env-file .env`.

```sh
alias dc='docker compose -f docker-compose.prod.yml --env-file .env'

dc pull

# 1. the data services first, and wait until they report healthy
dc up -d postgres redis opensearch
dc ps

# 2. the release step (ADR-0018): migrations, then the search index; exits non-zero if either fails
dc run --rm app ./release.sh

# 3. everything else
dc up -d
dc ps
```

Check that it works:

```sh
curl -fsS https://app.example.com/health   # Caddy got a certificate and reaches the API
dc logs --tail 50 app worker-ingest caddy
```

If Caddy logs certificate errors, the DNS record is not pointing at the VPS yet, or port 80 is blocked.

## 6. First User and Tenant

1. Open `https://app.example.com` and sign in with a magic link. The email comes through Resend, so check spam the first time.
2. Onboarding creates the Tenant, and its Owner gets the starting Credit grant (ADR-0017).
3. Upload a small PDF and wait until it is searchable. Then run one Search and one Ask. This checks S3 CORS, the worker, OpenSearch, Voyage and OpenAI in one go.

To give Credits later: `dc run --rm app python -m scripts.adjust_credits --tenant-id <uuid> --credits=<n> --note "<why>"`.

## 7. Backups: check them before you rely on them

The `pg-backup` service dumps Postgres nightly to `s3://kith-prod/backups/` and checks in to the Sentry Cron monitor. Run it once by hand, then **do the restore drill once**:

```sh
dc run --rm pg-backup            # take a dump now
# restore it into a throwaway database and look at it
dc exec postgres createdb -U kith restore_test
aws s3 cp s3://kith-prod/backups/<file>.sql.gz - | gunzip | dc exec -T postgres psql -U kith restore_test
dc exec postgres psql -U kith restore_test -c 'select count(*) from documents;'
dc exec postgres dropdb -U kith restore_test
```

OpenSearch has no backup. If it is lost, rebuild it from Postgres in the API container (ADR-0019):

```sh
dc exec app python -m scripts.rebuild_index
```

It asks you to type `yes` first (`--yes` skips that). Search comes back as each Document is re-indexed, and hybrid results once the worker has embedded it again. See `docs/search-quickstart.md` for what it does.

## 8. Turn on automatic deploys

Merge anything to `master`. Once the tests pass, `.github/workflows/deploy.yml` will:

1. build both images, tagged with the commit SHA, and push them to GHCR;
2. SSH in as `deploy`, copy the compose file and Caddyfile, and set `IMAGE_TAG`;
3. pull the images and run the release step. If it fails, the deploy stops and the old version keeps serving;
4. run `docker rollout app` and `docker rollout frontend`, then restart `worker-ingest`.

Every migration must work with the code that is still running (ADR-0018).

## Day-to-day

| Task | Command (on the VPS, in `/opt/kith`) |
|---|---|
| Follow logs | `dc logs -f app` (or `worker-ingest`, `frontend`, `caddy`) |
| Search JSON logs | `dc logs app --no-log-prefix \| jq 'select(.level=="ERROR")'` |
| Run a script | `dc exec app python -m scripts.<name> ...` |
| DB from your laptop | `ssh -L 5432:localhost:5432 deploy@<vps>`, then connect to `localhost:5432` |
| OpenSearch from your laptop | `ssh -L 9200:localhost:9200 deploy@<vps>`, then `curl localhost:9200/_cat/indices` |
| Roll back | re-run the deploy workflow with an older commit SHA (the schema is never downgraded) |
| Memory use | `docker stats --no-stream` |
