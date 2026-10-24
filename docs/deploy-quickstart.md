# Deploy quickstart (VPS, first time)

How to bring Kith up on a fresh VPS behind Caddy, from an empty server to a signed-in first User. After this first run, every merge to `master` deploys by itself. Why it is shaped this way: ADR-0018 (migrations as a release step), ADR-0019 (OpenSearch is rebuilt, not backed up), ADR-0012 (OpenSearch security off on the VPS).

## Checklist

Everything you do by hand, in order. The steps below say how.

1. Rent the VPS and point the domain at it (steps 1 and 2, DNS).
2. Create the outside resources: S3 bucket and IAM users, Resend, Sentry (step 2).
3. Make the deploy SSH key and fill in GitHub's secrets and variables (step 2, GitHub).
4. Prepare the VPS: the `deploy` user, firewall, Docker, the rollout plugin, GHCR login (step 3).
5. Write `/opt/kith/.env` on the VPS (step 4).
6. Run the first deploy from GitHub (step 5), then sign in (step 6).
7. Take a backup, schedule it, and do the restore drill once (step 7).

After that, merges to `master` deploy by themselves (step 8).

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
   - whole bucket: delete incomplete multipart uploads after 1 day. A large dump is uploaded in parts, and the backup's put-only keys cannot clean up after a failed upload.
4. Two IAM users, each with access keys. The app's keys must not be able to touch backups, so that a compromised API cannot delete them; the backup's keys can only add new dumps.
   - `kith-vps`, for the app (and for reading backups in the restore drill):

     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         { "Effect": "Allow", "Action": "s3:ListBucket", "Resource": "arn:aws:s3:::kith-prod" },
         {
           "Effect": "Allow",
           "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
           "Resource": "arn:aws:s3:::kith-prod/*"
         },
         {
           "Effect": "Deny",
           "Action": ["s3:PutObject", "s3:DeleteObject"],
           "Resource": "arn:aws:s3:::kith-prod/backups/*"
         }
       ]
     }
     ```

   - `kith-backup`, for the `pg-backup` service only, put-only under `backups/`:

     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         { "Effect": "Allow", "Action": "s3:PutObject", "Resource": "arn:aws:s3:::kith-prod/backups/*" }
       ]
     }
     ```

**Resend.** Add and verify your sending domain (SPF and DKIM records in DNS), then create an API key with "sending access" only. Its SMTP login is host `smtp.resend.com`, port `465`, user `resend`, password = the API key.

**Sentry.** It receives errors and a sample of traces from the API, the ingest worker and the frontend, with no personal data.

1. Create three projects, `kith-api` (platform: FastAPI), `kith-worker` (platform: Python) and `kith-frontend` (Next.js), and note each DSN (project settings → Client Keys). For the products, tick Error monitoring and Tracing only: logs stay on the VPS.
2. Add an **Uptime** monitor on `https://app.example.com/health`.
3. In the `kith-worker` project, add a **Cron** monitor with the slug `pg-backup`. The backup job checks in to it using the `kith-worker` DSN, so it needs no project of its own. Settings:
   - schedule: crontab `0 3 * * *`, timezone UTC (the same line as the crontab in step 7);
   - check-in margin: 30 minutes; max runtime: 30 minutes;
   - alert: when 1 check-in is missed or failed. You are then told when a night is missed, when the dump or upload fails, and when it hangs.
4. Limit the `kith-frontend` DSN. It is public (every browser sees it), and it can only send events, not read them, so the risk is someone flooding the project with fake errors:
   - project settings → Security & Privacy → **Allowed Domains**: `app.example.com`, so browser events from other sites are rejected;
   - project settings → Client Keys → the key → **Rate Limiting**: for example 100 events per minute, so a flood can't use up the quota.

**SSH keys** (on your laptop, e.g. WSL). Two key pairs, both for logging in to the VPS's `deploy` account (step 3). Each has a private half (no extension, stays secret) and a public half (`.pub`, given to the VPS).

| Key | Used by | Private half | Public half |
|---|---|---|---|
| yours, e.g. `~/.ssh/id_ed25519` | you, from your laptop | stays on your laptop | the provider's panel puts it on root; step 3 copies it to `deploy` |
| `kith-deploy` | GitHub Actions | GitHub secret `VPS_SSH_KEY` | added to `deploy` in step 3 |

Separate keys keep them independent: if the GitHub secret ever leaks, you delete CI's line on the VPS and yours keeps working.

```sh
# your own key; skip if ~/.ssh/id_ed25519 exists. Set a passphrase when asked.
ssh-keygen -t ed25519 -C "<you>-laptop"
cat ~/.ssh/id_ed25519.pub          # paste this into the provider's panel (SSH keys)

# CI's key: no passphrase (-N ''), since CI cannot type one. Writes kith-deploy and kith-deploy.pub.
ssh-keygen -t ed25519 -N '' -C kith-deploy -f kith-deploy
cat kith-deploy                    # the GitHub secret VPS_SSH_KEY (the whole file, BEGIN/END lines included)
cat kith-deploy.pub                # goes on the VPS in step 3
```

`-C` is only a label at the end of the public key, so you can tell keys apart in `authorized_keys`. It does not choose a user. Once `VPS_SSH_KEY` is saved in GitHub and `kith-deploy.pub` is on the VPS, delete the local `kith-deploy` files, so the private key exists only in GitHub (`rm kith-deploy kith-deploy.pub`). If you need it again, make a new pair.

**GitHub** (repo settings → Secrets and variables → Actions).

- Variables, which get baked into the frontend image at build time:
  - `NEXT_PUBLIC_API_URL` = `https://app.example.com`
  - `NEXT_PUBLIC_ASK_SHOW_SOURCES` = `true`
  - `NEXT_PUBLIC_ASK_CITATION_MARKERS` = `true`
  - `NEXT_PUBLIC_SENTRY_DSN` = the `kith-frontend` DSN (leave it unset to turn Sentry off in the frontend). The browser can see it; a DSN only lets someone send events, not read them. The image reports as `production`, traces 10 % of page loads (never `/health`), and carries the release SHA.
  - `NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE` (optional) = the frontend's share of traces, 0 to 1. Leave it unset for `0.1`. `SENTRY_TRACES_SAMPLE_RATE` in the server's `.env` sets only the backend's.
- Secrets, used by the deploy job to reach the VPS:
  - `VPS_HOST`: the address CI connects to, the VPS's public IP (e.g. `203.0.113.10`, from your hosting provider's panel) or a hostname pointing at it
  - `VPS_USER`: the Linux user CI logs in as on the VPS, `deploy` (created in step 3)
  - `VPS_SSH_KEY`: the content of `kith-deploy`, CI's private key (above)
- One more variable, `VPS_KNOWN_HOSTS`: the VPS's own SSH key (its host key), so CI refuses to deploy to any other machine answering at `VPS_HOST`. It already exists on the VPS; you don't create it. It is public, so it is a variable, not a secret. Print it on the VPS:

  ```sh
  cat /etc/ssh/ssh_host_ed25519_key.pub
  # ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... root@srv123
  ```

  The value is one line: exactly what you put in `VPS_HOST` (the IP, or the hostname if you used one), a space, then the first two parts of that output (drop the trailing label):

  ```
  203.0.113.10 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI...
  ```

Application secrets (API keys, database password) never go to GitHub: they live only in the VPS's `.env` (step 4).

## 3. Prepare the VPS

### The `deploy` user, SSH and firewall

Your hosting provider's panel (on Hostinger, the VPS's SSH keys setting) puts your SSH key on **root**, so the first login is `ssh root@<VPS_IP>` from your laptop. Each account has its own list of allowed keys, so root's key does not let you in as any other user.

These steps add a second account, `deploy`. You and CI log in to it to run Kith, and root login is then turned off:

- bots try `ssh root@…` on every server all day, so it should not be open;
- CI's key gets its own line, which you can delete if the GitHub secret ever leaks, without touching your own access;
- `/opt/kith`, its `.env` and the backup's crontab belong to `deploy`, so Kith never runs as root by accident.

`deploy` is in the `docker` group (below), which can do almost anything root can, so treat its keys as carefully as root's.

**1. Create `deploy` and give it the keys.** As root on the VPS:

Create the account. It has no password: only SSH keys get in.

```sh
adduser --disabled-password --gecos "" deploy
```

Copy your own key (the one the provider's panel put on root) to it:

```sh
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

Add CI's key: open the file and paste the content of `kith-deploy.pub` (made in step 2 → GitHub) as a new line at the end.

```sh
nano /home/deploy/.ssh/authorized_keys
```

**2. Check `deploy` works before going further.** Keep the root session open. In a **second terminal on your laptop**:

```sh
ssh deploy@<VPS_IP>    # must log you in without a password
```

If it fails, fix it from the root session first. The next step locks root out, and you'd be left with only the provider's browser terminal.

**3. Keys only, no root login, firewall, automatic security updates.** Back in the root session:

```sh
# a drop-in file read before the others in sshd_config.d (the first value set wins), so a
# provider's own file there (e.g. 50-cloud-init.conf) cannot turn password login back on
printf 'PasswordAuthentication no\nPermitRootLogin no\n' > /etc/ssh/sshd_config.d/00-kith.conf
sshd -t && systemctl restart ssh
sshd -T | grep -E '^(passwordauthentication|permitrootlogin) '   # both must say "no"

# firewall
ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw enable

# security updates install themselves
apt update && apt install -y unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades
```

From now on, log in with `ssh deploy@<VPS_IP>`. Admin tasks that need root later (`apt`, `ufw`, SSH settings) go through the provider's panel. Open its browser terminal now and check it still gets you a root shell. Some panels log in over SSH, which root login being off now blocks. If it does not, the panel's recovery mode still gives root access, or you can undo the lock by deleting `/etc/ssh/sshd_config.d/00-kith.conf` from there.

### Provider firewall

In your hosting provider's control panel, add a firewall for the VPS that allows only inbound TCP 22, 80 and 443 (and UDP 443 for HTTP/3). It runs outside the server, so Docker cannot bypass it the way it bypasses `ufw` (see below): if a container ever publishes a port by mistake, this still blocks it.

### Docker

Install Docker Engine and the compose plugin by following https://docs.docker.com/engine/install/ubuntu/, then:

```sh
usermod -aG docker deploy   # being in the docker group is the same as being root, so only this user gets it
```

> Docker bypasses `ufw` for published ports. A `ports: "5432:5432"` line would open Postgres to the internet whatever `ufw` says. That is why the prod compose file publishes only Caddy's ports, and binds Postgres and OpenSearch to `127.0.0.1`.

### Log rotation

So container logs cannot fill the disk. In `/etc/docker/daemon.json`:

```json
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }
```

Then `systemctl restart docker`.

### OpenSearch memory maps

OpenSearch will not start without this (same as in `docs/search-quickstart.md`):

```sh
echo 'vm.max_map_count=262144' > /etc/sysctl.d/99-opensearch.conf && sysctl --system
```

### Install the rollout plugin (`docker rollout`)

Every deploy needs it: `deploy.sh` uses it to replace `app` and `frontend` without downtime, and fails without it. Run as `deploy`:

```sh
mkdir -p ~/.docker/cli-plugins
# the version CI's smoke test uses (.github/actions/smoke-test)
curl -fsSL https://raw.githubusercontent.com/wowu/docker-rollout/v0.14/docker-rollout -o ~/.docker/cli-plugins/docker-rollout
chmod +x ~/.docker/cli-plugins/docker-rollout
docker rollout --help
```

### GHCR login

Needed only if the images are private (GHCR makes them private when the deploy workflow first pushes them; you can make each package public in its settings instead). As `deploy`, with a GitHub personal access token that has `read:packages` only:

```sh
echo <token> | docker login ghcr.io -u <github-user> --password-stdin
```

## 4. Put the config on the VPS

Everything lives in `/opt/kith`, owned by `deploy`:

```sh
sudo mkdir -p /opt/kith && sudo chown deploy:deploy /opt/kith
```

The deploy job copies `docker-compose.prod.yml`, `Caddyfile`, `pg-backup.sh` and `deploy.sh` from the repo on every deploy, so the server always matches the commit it runs. Only `.env` is yours to write.

The secrets go in `/opt/kith/.env`: the database password, the S3, Resend, Sentry, OpenAI and Voyage keys, and the site's address. The containers read their settings from it, and it is the only place those secrets exist: not in git, not in GitHub, and CI never sees them. Write it by hand, keep it readable by `deploy` only (`chmod 600`), and never commit it. The deploy never overwrites it; it only updates the `IMAGE_TAG` line.

```sh
touch /opt/kith/.env && chmod 600 /opt/kith/.env && nano /opt/kith/.env
```

```sh
# ── site ──
DOMAIN=app.example.com
# IMAGE_TAG (the commit SHA running) is added and kept up to date by
# deploy.sh; leave it out.

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
# the pg-backup service's own keys (put-only under backups/)
BACKUP_AWS_ACCESS_KEY_ID=<kith-backup key>
BACKUP_AWS_SECRET_ACCESS_KEY=<kith-backup secret>

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
# also used by pg-backup to check in to its Cron monitor
SENTRY_WORKER_DSN=<kith-worker dsn>
# share of requests and jobs traced (0 to 1; /health is never traced)
SENTRY_TRACES_SAMPLE_RATE=0.1
```

The compose file reads this file twice: it fills in `${...}` values in `docker-compose.prod.yml` (missing ones stop it from starting), and it hands the whole file to `app` and `worker-ingest` as their settings. The other services get only what they need. The internal addresses (`DATABASE_URL`, built from the `POSTGRES_*` values, `REDIS_URL`, `SEARCH_URL`, the frontend's `BACKEND_URL`) are set in the compose file, so they are not in `.env`.

The other settings (upload caps, retrieval sizes, `STARTING_CREDIT_GRANT`, ...) have working defaults. Add one here only to change it. Tuning knobs with defaults: `GUNICORN_WORKERS` (2), `GUNICORN_GRACEFUL_TIMEOUT` (30 seconds, how long an Ask stream gets to finish on a deploy), `OPENSEARCH_HEAP` (`512m`).

## 5. First start

The deploy workflow pushes both images to GHCR on every merge to `master`. If the VPS was not ready when it ran, that run's deploy job failed at SSH; that is expected, and its images are in GHCR all the same.

Start the stack by running the deploy workflow by hand: GitHub → Actions → **Deploy** → Run workflow, with `image_tag` = the full SHA of that `master` commit (`git rev-parse origin/master`). It is the same job every later deploy runs (step 8), and `deploy.sh` also starts a fresh server: it starts Postgres, Redis and OpenSearch and waits for them, runs the release step, then the API, frontend, worker and Caddy start.

From here on `dc` means `docker compose -f docker-compose.prod.yml --env-file .env`, run as `deploy` in `/opt/kith`:

```sh
alias dc='docker compose -f docker-compose.prod.yml --env-file .env'
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

The `pg-backup` service dumps Postgres (`pg_dump` custom format, compressed) to `s3://kith-prod/backups/<POSTGRES_DB>-<UTC timestamp>.dump`, and checks in to the Sentry Cron monitor when it starts, succeeds or fails. It is in the `backup` profile, so `dc up -d` never starts it; `dc run` does, building its small image (Postgres client and AWS CLI) the first time. S3 deletes dumps after 14 days.

**Take one by hand**, now and before any risky change:

```sh
dc run --rm pg-backup     # prints "pg-backup: uploaded s3://..." and exits 0
```

**Schedule it nightly** in the `deploy` user's crontab (`crontab -e`). The time matches the Cron monitor's schedule (the VPS clock is UTC; check with `date`):

```
0 3 * * * cd /opt/kith && docker compose -f docker-compose.prod.yml --env-file .env run --rm -T pg-backup 2>&1 | logger -t pg-backup
```

Its output goes to the system log: `journalctl -t pg-backup`.

**Do the restore drill once**, so you know a dump actually restores. It runs in the backup image with the `kith-vps` keys, which can read `backups/` (the backup's own keys can only write):

```sh
# the kith-vps keys from .env, passed into the container below
export AWS_ACCESS_KEY_ID=$(sed -n 's/^AWS_ACCESS_KEY_ID=//p' .env)
export AWS_SECRET_ACCESS_KEY=$(sed -n 's/^AWS_SECRET_ACCESS_KEY=//p' .env)
restore() { dc run --rm -T -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY --entrypoint sh pg-backup -c "$1"; }

# 1. pick a dump
restore 'aws s3 ls "s3://$S3_BUCKET/backups/"'

# 2. restore it into a throwaway database
dc exec postgres createdb -U kith restore_test
restore 'aws s3 cp --only-show-errors "s3://$S3_BUCKET/backups/<file>.dump" /tmp/restore.dump && pg_restore --no-owner --exit-on-error --dbname restore_test /tmp/restore.dump'

# 3. the Documents count matches the live database (as of the dump)
for db in kith restore_test; do dc exec postgres psql -U kith -d "$db" -tAc 'select count(*) from documents'; done

# 4. clean up
dc exec postgres dropdb -U kith restore_test
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
```

To recover after losing the server, do the same into the `kith` database of a fresh stack (before the release step), then rebuild the search index as below.

OpenSearch has no backup. If it is lost, rebuild it from Postgres in the API container (ADR-0019):

```sh
dc exec app python -m scripts.rebuild_index
```

It asks you to type `yes` first (`--yes` skips that). Search comes back as each Document is re-indexed, and hybrid results once the worker has embedded it again. See `docs/search-quickstart.md` for what it does.

## 8. Automatic deploys

`.github/workflows/deploy.yml` runs on every push to `master`:

1. the backend tests and the frontend build and tests;
2. it builds both images, tagged with the commit SHA and `latest`;
3. it smoke-tests those images as a running stack: Caddy's routing, then a second deploy while `/health` and `/` are polled, where no request may fail;
4. it pushes those same images to GHCR;
5. it SSHes in as `deploy`, copies the compose file, Caddyfile, `pg-backup.sh` and `deploy.sh` into `/opt/kith`, and runs `deploy.sh <sha>`, which:
   1. pulls the images, and starts Postgres, Redis and OpenSearch if they are not running;
   2. runs the release step. If it fails, the deploy stops there and the old version keeps serving;
   3. records the SHA as `IMAGE_TAG` in `.env`;
   4. runs `docker rollout app` and `docker rollout frontend`, then restarts `worker-ingest`;
   5. starts anything not running yet and reloads Caddy's config.

A failed test or smoke check stops it before the push. Only one deploy runs at a time: a running deploy is never cancelled, and when several merges queue up behind it, only the newest one deploys.

Every migration must work with the code that is still running (ADR-0018).

During the swap, a request that reaches the old `app` container while it shuts down can take 1 to 3 seconds longer. None fail (the smoke test checks that).

A change to a data service in `docker-compose.prod.yml` (Postgres, Redis, OpenSearch) is copied but not applied, so a deploy never restarts the database by surprise. Apply it by hand: `dc up -d <service>`.

**Roll back** by running the workflow by hand (Actions → Deploy → Run workflow) with an older full commit SHA as `image_tag`. It skips testing and building, and deploys that commit's images with that commit's compose file and Caddyfile. The schema is never downgraded. A rollback waits behind a running deploy like any run, and a merge that arrives while it waits replaces it, so check it ran. After each deploy the VPS prunes images built over a week ago that no container uses; a rollback pulls an older one again from GHCR.

## Day-to-day

| Task | Command (on the VPS, in `/opt/kith`) |
|---|---|
| Follow logs | `dc logs -f app` (or `worker-ingest`, `frontend`, `caddy`) |
| Search JSON logs | `dc logs app --no-log-prefix \| jq 'select(.level=="ERROR")'` |
| Run a script | `dc exec app python -m scripts.<name> ...` |
| DB from your laptop | `ssh -L 5432:localhost:5432 deploy@<vps>`, then connect to `localhost:5432` |
| OpenSearch from your laptop | `ssh -L 9200:localhost:9200 deploy@<vps>`, then `curl localhost:9200/_cat/indices` |
| Roll back | Actions → Deploy → Run workflow with an older full commit SHA (step 8) |
| Deploy by hand | `sh deploy.sh <full commit sha>` (what the workflow runs) |
| Memory use | `docker stats --no-stream` |
