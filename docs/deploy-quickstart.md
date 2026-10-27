# Deploy quickstart (VPS, first time)

How to bring Kith up on a fresh VPS behind Caddy, from an empty server to a signed-in first User. After this first run, every merge to `master` deploys by itself. Why it is shaped this way: ADR-0018 (migrations as a release step), ADR-0019 (OpenSearch is rebuilt, not backed up), ADR-0012 (OpenSearch security off on the VPS).

## Checklist

Everything you do by hand, in order. The steps below say how.

1. Rent the VPS and point the domain at it (steps 1 and 2, DNS).
2. Create the outside resources: S3 bucket and IAM users, Resend, Sentry (step 2).
3. Make the deploy SSH key and fill in GitHub's secrets and variables (step 2, GitHub).
4. Prepare the VPS: the `deploy` user, then everything that needs root (firewall, Docker, `/opt/kith`), then lock root out; then, as `deploy`, the rollout plugin and the GHCR login with a GitHub token (step 3).
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
- A domain you can add DNS records to. Below it is `example.com`; Kith is served on it, and `www.example.com` redirects to it.
- Accounts: AWS, Resend, Sentry, OpenAI, Voyage.
- Admin access to the GitHub repo.

## 2. Outside resources (one time, by hand)

**DNS.** `A` records (and `AAAA` if the VPS has IPv6) for `example.com` and `www.example.com`, both pointing at the VPS. Caddy needs them in place before it can get the HTTPS certificates. It gets one for each, and redirects `www.example.com/<path>` to `example.com/<path>` permanently (`DOMAIN` in `.env` is the bare domain; the `www.` site comes from it).

**AWS S3.** Use the region closest to the VPS.

1. Create a bucket, e.g. `kith-prod`, with "Block all public access" on. The app uses presigned URLs, so nothing in it is ever public.
2. CORS: the browser uploads PDFs straight to S3 and loads previews from it (ADR-0009).

   ```json
   [
     {
       "AllowedOrigins": ["https://example.com"],
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
         {
           "Effect": "Allow",
           "Action": "s3:ListBucket",
           "Resource": "arn:aws:s3:::kith-prod"
         },
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
         {
           "Effect": "Allow",
           "Action": "s3:PutObject",
           "Resource": "arn:aws:s3:::kith-prod/backups/*"
         }
       ]
     }
     ```

**Resend.** Add and verify your sending domain (SPF and DKIM records in DNS), then create an API key with "sending access" only. Its SMTP login is host `smtp.resend.com`, port `465`, user `resend`, password = the API key.

**Sentry.** It receives errors and a sample of traces from the API, the ingest worker and the frontend, with no personal data.

1. Create three projects, `kith-api` (platform: FastAPI), `kith-worker` (platform: Python) and `kith-frontend` (Next.js), and note each DSN (project settings → Client Keys). For the products, tick Error monitoring and Tracing only: logs stay on the VPS.
2. Add an **Uptime** monitor on `https://example.com/health`.
3. In the `kith-worker` project, add a **Cron** monitor with the slug `pg-backup`. The backup job checks in to it using the `kith-worker` DSN, so it needs no project of its own. Settings:
   - schedule: crontab `0 3 * * *`, timezone UTC (the same line as the crontab in step 7);
   - check-in margin: 30 minutes; max runtime: 30 minutes;
   - alert: when 1 check-in is missed or failed. You are then told when a night is missed, when the dump or upload fails, and when it hangs.
4. Limit the `kith-frontend` DSN. It is public (every browser sees it), and it can only send events, not read them, so the risk is someone flooding the project with fake errors:
   - project settings → Security & Privacy → **Allowed Domains**: `example.com`, so browser events from other sites are rejected;
   - project settings → Client Keys → the key → **Rate Limiting**: for example 100 events per minute, so a flood can't use up the quota.

**SSH keys** (on your laptop, e.g. WSL). Two key pairs, both for logging in to the VPS's `deploy` account (step 3). Each has a private half (no extension, stays secret) and a public half (`.pub`, given to the VPS).

| Key                             | Used by               | Private half                | Public half                                                        |
| ------------------------------- | --------------------- | --------------------------- | ------------------------------------------------------------------ |
| yours, e.g. `~/.ssh/id_ed25519` | you, from your laptop | stays on your laptop        | the provider's panel puts it on root; step 3 copies it to `deploy` |
| `kith-deploy`                   | GitHub Actions        | GitHub secret `VPS_SSH_KEY` | added to `deploy` in step 3                                        |

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

`-C` is only a label at the end of the public key, so you can tell keys apart in `authorized_keys`. It does not choose a user.

Never copy the private `kith-deploy` file to the VPS. Only `kith-deploy.pub` goes there: the server only checks keys and never logs in with one, and a private key left on it would let anyone who broke in reuse it. You can tell the halves apart: the private file is several lines between `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`; the `.pub` is one line starting with `ssh-ed25519`.

Once `VPS_SSH_KEY` is saved in GitHub and `kith-deploy.pub` is on the VPS, delete the local `kith-deploy` files, so the private key exists only in GitHub (`rm kith-deploy kith-deploy.pub`). If you need it again, make a new pair.

**GitHub** (repo settings → Secrets and variables → Actions).

- Variables, which get baked into the frontend image at build time:
  - `NEXT_PUBLIC_API_URL` = `https://example.com`
  - `NEXT_PUBLIC_ASK_SHOW_SOURCES` = `true`
  - `NEXT_PUBLIC_ASK_CITATION_MARKERS` = `true`
  - `NEXT_PUBLIC_SENTRY_DSN` = the `kith-frontend` DSN (leave it unset to turn Sentry off in the frontend). The browser can see it; a DSN only lets someone send events, not read them. The image reports as `production`, traces 10 % of page loads (never `/health`), and carries the release SHA.
  - `NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE` (optional) = the frontend's share of traces, 0 to 1. Leave it unset for `0.1`. `SENTRY_TRACES_SAMPLE_RATE` in the server's `.env` sets only the backend's.
- Secrets, used by the deploy job to reach the VPS:
  - `VPS_HOST`: the address CI connects to, the VPS's public IP (e.g. `203.0.113.10`, from your hosting provider's panel) or a hostname pointing at it
  - `VPS_USER`: the Linux user CI logs in as on the VPS, `deploy` (created in step 3)
  - `VPS_SSH_KEY`: the whole `kith-deploy` file, CI's private key (above). Not the `.pub`. Run `cat kith-deploy` and paste everything it prints, from `-----BEGIN OPENSSH PRIVATE KEY-----` to `-----END OPENSSH PRIVATE KEY-----`, both lines included. The deploy job checks it before connecting, and stops with an error if it is the `.pub`, cut short, or has a passphrase.
- One more variable, `VPS_KNOWN_HOSTS`: the VPS's **host key**, the server's own SSH key that proves which machine it is. CI checks it before connecting, so it refuses any other machine answering at that address. The host key was made when the VPS was installed, so you don't create it, only copy it. It is public, so `VPS_KNOWN_HOSTS` is a variable, not a secret. Print the host key on the VPS:

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

`deploy` is in the `docker` group (step 3 below), which can do almost anything root can, so treat its keys as carefully as root's.

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

If it fails, fix it from the root session first. Step 4 locks root out, and you'd be left with only the provider's browser terminal.

**3. Everything that needs root.** Back in the root session. `deploy` has no `sudo`, so all of this must be done now, before step 4 locks root out.

Firewall, and security updates that install themselves:

```sh
ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw enable
apt update && apt install -y unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades
```

Docker Engine and the compose plugin: follow https://docs.docker.com/engine/install/ubuntu/ ("Install using the apt repository"). Its commands start with `sudo`; as root they work with or without it. Then put `deploy` in the `docker` group. Being in it is the same as being root, so only this user gets it:

```sh
usermod -aG docker deploy
```

> Docker bypasses `ufw` for published ports. A `ports: "5432:5432"` line would open Postgres to the internet whatever `ufw` says. That is why the prod compose file publishes only Caddy's ports, and binds Postgres and OpenSearch to `127.0.0.1`.

Container logs go to the system journal, so they outlive the containers a deploy replaces. Each entry carries its Compose service name (`journalctl COM_DOCKER_COMPOSE_SERVICE=app`, see `vps-operations.md`), and the journal is capped at 1 GB, dropping the oldest entries first, so logs cannot fill the disk:

```sh
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=persistent\nSystemMaxUse=1G\n' > /etc/systemd/journald.conf.d/00-kith.conf
systemctl restart systemd-journald
echo '{ "log-driver": "journald", "log-opts": { "labels": "com.docker.compose.service" } }' > /etc/docker/daemon.json
systemctl restart docker
docker info --format '{{.LoggingDriver}}'   # must print "journald"
```

`Storage=persistent` keeps the journal on disk across reboots. `dc logs` (step 5) still works with this driver.

> **A VPS that already runs Kith** with the old `json-file` setting needs its containers recreated too: see "Move a VPS from `json-file` logs to the journal" in `vps-operations.md`.

Memory maps: OpenSearch will not start without this (same as in `docs/search-quickstart.md`):

```sh
echo 'vm.max_map_count=262144' > /etc/sysctl.d/99-opensearch.conf && sysctl --system
```

The folder Kith lives in, owned by `deploy` (step 4 fills it):

```sh
mkdir -p /opt/kith && chown deploy:deploy /opt/kith
```

**4. Keys only, no root login.** Still in the root session:

```sh
# a drop-in file read before the others in sshd_config.d (the first value set wins), so a
# provider's own file there (e.g. 50-cloud-init.conf) cannot turn password login back on
printf 'PasswordAuthentication no\nPermitRootLogin no\n' > /etc/ssh/sshd_config.d/00-kith.conf
sshd -t && systemctl restart ssh
sshd -T | grep -E '^(passwordauthentication|permitrootlogin) '   # both must say "no"
```

From now on, log in with `ssh deploy@<VPS_IP>`. If you were already logged in as `deploy`, log out and back in: the `docker` group only applies to new sessions. `docker ps` must print an empty table, not "permission denied".

### Getting root back later

Some later admin tasks need root (`apt`, `ufw`, SSH settings, anything you missed in step 3). Two ways in:

- **The provider's panel.** Its browser terminal or its recovery mode gives you a root shell. Check now that one of them works. Some browser terminals log in over SSH, which root login being off now blocks; recovery mode works either way.
- **Turn root SSH back on for a while, keys only.** From the panel's root shell:

  ```sh
  sed -i 's/^PermitRootLogin no$/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config.d/00-kith.conf
  sshd -t && systemctl restart ssh
  ```

  `ssh root@<VPS_IP>` works again with your key (passwords stay off). When you are done, lock it again:

  ```sh
  sed -i 's/^PermitRootLogin prohibit-password$/PermitRootLogin no/' /etc/ssh/sshd_config.d/00-kith.conf
  sshd -t && systemctl restart ssh
  ```

### Provider firewall

In your hosting provider's control panel, add a firewall for the VPS that allows only inbound TCP 22, 80 and 443 (and UDP 443 for HTTP/3). It runs outside the server, so Docker cannot bypass it the way it bypasses `ufw` (see above): if a container ever publishes a port by mistake, this still blocks it.

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

The VPS downloads the images from GHCR, and they are private: GHCR makes them private when the deploy workflow first pushes them. Keep them that way while the repo is private, since the backend image contains the Python source. So the VPS needs a GitHub token that can only download images.

**Create the token** on GitHub, logged in as yourself. It must be a **classic** token, because GHCR does not accept the fine-grained kind.

1. Profile picture → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**.
2. Note: `kith-vps-ghcr-pull`.
3. Expiration: pick a date and put a reminder in your calendar. Once it expires, deploys fail at the image pull and the old version keeps serving; make a new token and log in again (below). "No expiration" avoids that, but a leaked token then works forever.
4. Scopes: tick **only `read:packages`**, so it can download images and nothing else.
5. **Generate token**, and copy it now: GitHub shows it once.

**Log in on the VPS**, as `deploy`:

```sh
echo <token> | docker login ghcr.io -u <your-github-username> --password-stdin
```

Docker keeps the login in `/home/deploy/.docker/config.json`, so this is done once per token. The token goes nowhere else: not in `.env`, and not in GitHub's secrets (CI pushes with its own built-in token).

## 4. Put the config on the VPS

Everything lives in `/opt/kith`, which step 3 created and gave to `deploy`. Run this step as `deploy`.

The deploy job copies `docker-compose.prod.yml`, `Caddyfile`, `pg-backup.sh` and `deploy.sh` from the repo on every deploy, so the server always matches the commit it runs. Only `.env` is yours to write.

The secrets go in `/opt/kith/.env`: the database password, the S3, Resend, Sentry, OpenAI and Voyage keys, and the site's address. The containers read their settings from it, and it is the only place those secrets exist: not in git, not in GitHub, and CI never sees them. Write it by hand, keep it readable by `deploy` only (`chmod 600`), and never commit it. The deploy never overwrites it; it only updates the `IMAGE_TAG` line.

```sh
touch /opt/kith/.env && chmod 600 /opt/kith/.env && nano /opt/kith/.env
```

```sh
# ── site ──
DOMAIN=example.com
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
CORS_ALLOWED_ORIGINS=https://example.com
MAGIC_LINK_VERIFY_URL=https://example.com/verify
SESSION_COOKIE_SECURE=true
APP_URL=https://example.com

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

### Changing `.env` later

Containers read `.env` only when they are created. A restart keeps the old values, so the containers have to be recreated. From your laptop:

```sh
# 1. log in to the VPS as deploy
ssh deploy@<vps>

# 2. edit the file, save (Ctrl+O, Enter) and quit (Ctrl+X)
nano /opt/kith/.env

# 3. recreate the containers that use .env
docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env up -d --no-deps app worker-ingest frontend caddy

# 4. check they started with the new values (an error such as
#    STORAGE_PROVIDER=S3 being rejected shows up here)
docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env logs --tail 50 app worker-ingest
```

Step 3 recreates only the containers whose settings changed; the others keep running. `--no-deps` leaves Postgres, Redis and OpenSearch alone, as `deploy.sh` does. The site is down for a few seconds while `app` is recreated.

Changing a `POSTGRES_*` value does not change the database itself: Postgres reads them only when it first creates its data. Change the password inside Postgres first, then in `.env`.

## 5. First start

The deploy workflow pushes both images to GHCR on every merge to `master`. If the VPS was not ready when it ran, that run's deploy job failed at SSH; that is expected, and its images are in GHCR all the same.

Start the stack by running the deploy workflow by hand: GitHub → Actions → **Deploy** → Run workflow, with `image_tag` = the full SHA of that `master` commit (`git rev-parse origin/master`). It is the same job every later deploy runs (step 8), and `deploy.sh` also starts a fresh server: it starts Postgres, Redis and OpenSearch and waits for them, runs the release step, then the API, frontend, worker and Caddy start.

From here on `dc` means `docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env`, run as `deploy`. The full paths make it work from any folder:

```sh
alias dc='docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env'
dc ps
```

Check that it works:

```sh
curl -fsS https://example.com/health   # Caddy got a certificate and reaches the API
dc logs --tail 50 app worker-ingest caddy
```

If Caddy logs certificate errors, the DNS record is not pointing at the VPS yet, or port 80 is blocked.

## 6. First User and Tenant

1. Open `https://example.com` and sign in with a magic link. The email comes through Resend, so check spam the first time.
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
0 3 * * * docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env run --rm -T pg-backup 2>&1 | logger -t pg-backup
```

Its output goes to the system log: `journalctl -t pg-backup`.

**Do the restore drill once**, so you know a dump actually restores. It runs in the backup image with the `kith-vps` keys, which can read `backups/` (the backup's own keys can only write):

```sh
# the kith-vps keys from .env, passed into the container below
export AWS_ACCESS_KEY_ID=$(sed -n 's/^AWS_ACCESS_KEY_ID=//p' /opt/kith/.env)
export AWS_SECRET_ACCESS_KEY=$(sed -n 's/^AWS_SECRET_ACCESS_KEY=//p' /opt/kith/.env)
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

## Load tests (planned, not built yet)

k6 load tests run against a second VPS on the same plan as prod, never against prod (ADR-0021). Pushing a `loadtest-load-<name>` tag runs a Load test at `LOADTEST_VUS` virtual users; a `loadtest-stress-<name>` tag adds users up to `LOADTEST_STRESS_MAX_VUS` and reports the breaking point. Deleting the tag cancels the run and resets the test data. Results go to S3 under `loadtest/` and by email; metrics go to Grafana Cloud (ADR-0022). The spec is #158. Each ticket below replaces its line with the real steps once it is built.

What you will do by hand, in order:

1. Get a Hostinger API token, create the state bucket and its key, make the SSH keys, buy the load-test VPS with `terraform apply` and bring Kith up on it ("Load-test VPS" below, #159).
2. Create the load-test OpenAI key, in its own Project with a $20/month budget, and a separate Voyage key; run the seed build once (#162).
3. Run your own concurrency check and set the `LOADTEST_VUS` GitHub variable; push the first `loadtest-load-*` tag (#163).
4. Add the Resend key and the recipient address as GitHub secrets (#164).
5. Set the `LOADTEST_STRESS_MAX_VUS` GitHub variable; push the first `loadtest-stress-*` tag (#165).
6. Create the Grafana Cloud Free stack and its tokens (#167).
7. Add the Grafana Cloud metrics token to prod's `.env` and test the alert email (#168).

### Load-test VPS

The machine is made by Terraform (`infra/loadtest/hostinger`), which only buys it and outputs its address and SSH user. `infra/loadtest/setup.sh` then turns it into the Kith stack, with the same compose file, Caddyfile and `deploy.sh` as prod. The setup script knows nothing about Hostinger: on another provider, only the Terraform module and `recreate.sh` change. Terraform manages this VPS only, never prod or anything on AWS. You need Terraform 1.11 or later, the AWS CLI and `jq` on your laptop.

**1. Hostinger API token.** hPanel → profile → **API** → new token. If the page is missing, the account can't make tokens yet; ask Hostinger support. Keep it for your laptop (`export HOSTINGER_API_TOKEN=...`) and add it as the GitHub secret `HOSTINGER_API_TOKEN`.

**2. The state bucket.** Terraform keeps its state in S3, never in git, and locks it while an apply runs (S3's own lock file, so no DynamoDB table).

1. Create the bucket `kith-terraform-state` in the same region as prod's, with "Block all public access" on and **versioning on** (a bad apply can then be undone from an older state).
2. IAM user `kith-terraform`, with access keys and only this policy:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "s3:ListBucket",
         "Resource": "arn:aws:s3:::kith-terraform-state"
       },
       {
         "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
         "Resource": "arn:aws:s3:::kith-terraform-state/loadtest/*"
       }
     ]
   }
   ```

   `DeleteObject` is for the lock file, which is removed when an apply ends.

3. GitHub secrets `TERRAFORM_AWS_ACCESS_KEY_ID` and `TERRAFORM_AWS_SECRET_ACCESS_KEY`, and the variable `TERRAFORM_AWS_REGION`. On your laptop, the same three as `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_REGION`.

**3. SSH keys.** Two key pairs, as for prod (step 2 → SSH keys), plus the server's own **host key**. A reinstall would normally give the VPS a new host key, so CI would refuse to connect after every `recreate`. Hostinger's post-install script puts this one back each time, and the known_hosts line never changes.

```sh
ssh-keygen -t ed25519 -N '' -C kith-loadtest -f ~/.ssh/kith-loadtest           # CI's login key
ssh-keygen -t ed25519 -N '' -C kith-loadtest-host -f ~/.ssh/kith-loadtest-host # the VPS's host key
```

Each command writes a private file (no extension, the secret) and a `.pub` file (public, safe to share). Where each one goes:

| File | Goes to |
|---|---|
| `kith-loadtest` (private) | GitHub secret `LOADTEST_SSH_KEY`, then delete it from your laptop |
| `kith-loadtest.pub` | `authorized_keys` in `terraform.tfvars`, so CI can log in |
| `kith-loadtest-host` (private) | GitHub secret `LOADTEST_SSH_HOST_KEY`; keep it on your laptop too, since every `terraform apply` from there needs it |
| `kith-loadtest-host.pub` | your `~/.ssh/known_hosts` (step 7); CI builds its own line from the private file |
| your `~/.ssh/id_ed25519.pub` | `authorized_keys` in `terraform.tfvars`, so you can log in |

**4. Buy the VPS with Terraform.** Find the IDs of prod's data center and of Ubuntu 24.04, and check the plan is still listed:

For jq if not installed: sudo apt update && sudo apt install -y jq

```sh
call() { curl -fsS -H "Authorization: Bearer $HOSTINGER_API_TOKEN" "https://developers.hostinger.com/api/$1"; }
call vps/v1/data-centers | jq '.[] | {id, name, city}'
call vps/v1/templates | jq '.[] | select(.name | test("Ubuntu 24.04")) | {id, name}'
call billing/v1/catalog | jq '.[] | select(.name | test("KVM 2")) | .prices[] | {id, period, period_unit, price}'
```

Fill in `infra/loadtest/hostinger/terraform.tfvars`. It stays on your laptop (it is in `.gitignore`). CI gets the same values from the GitHub variables `TF_VAR_data_center_id`, `TF_VAR_template_id` and `TF_VAR_authorized_keys`; the last one is the list as written below, brackets included. Terraform reads `TF_VAR_<name>` variables by itself.

```hcl
data_center_id = 0 # prod's
template_id    = 0 # Ubuntu 24.04
# plan defaults to hostingercom-vps-kvm2-usd-1m; a 12m or 24m item is cheaper per month but paid upfront
authorized_keys = [
  "ssh-ed25519 AAAA... your-laptop",
  "ssh-ed25519 AAAA... kith-loadtest",
]
```

Then, in that folder:

```sh
export TF_VAR_ssh_host_key="$(cat ~/.ssh/kith-loadtest-host)"
terraform init
terraform apply      # charges the account's default payment method for the plan
terraform apply      # again: must say "No changes"
terraform output     # address and ssh_user
```

The first apply buys the VPS, like ordering it in hPanel.

**If the apply fails with `HTTP 202` / `payment_initiated`**, or you bought the VPS in hPanel, the VPS exists but Terraform's state doesn't know it. **Do not apply again: it would buy another one.** Adopt it instead:

1. Wait until the order completes and the VPS is listed: `curl -fsS -H "Authorization: Bearer $HOSTINGER_API_TOKEN" https://developers.hostinger.com/api/vps/v1/virtual-machines | jq '.[] | {id, hostname, state, plan}'`. If its `state` is `initial`, set it up in hPanel with the same Ubuntu as prod (any root password).
2. `terraform import hostinger_vps.loadtest <id>`, then `terraform plan`. It must say `0 to add` and `0 to destroy`. If it wants to replace the VPS, the term differs: set `plan` in `terraform.tfvars` to the one the import read (`terraform state show hostinger_vps.loadtest`).
3. `terraform apply`, then `sh recreate.sh` once: the VPS was installed without the post-install script, so the reinstall puts the keys and host key on it.
 `terraform destroy` is blocked on purpose: on Hostinger it cancels the subscription. To give the machine up, remove `prevent_destroy` in `main.tf` in a reviewed change first.

Where `terraform apply` runs:

- **The first one, from your laptop.** It buys the VPS and charges the card, and Hostinger may ask you to finish the order in hPanel, so watch it.
- **Then from the load-test workflow, at the start of each tagged run (#163).** It normally changes nothing; it checks the VPS is there before the reinstall and setup.
- **Never on a push to `master`.** A merge deploys prod, which Terraform doesn't manage. On pull requests and `master`, CI only runs `fmt -check` and `validate`, which never reach Hostinger.

Your laptop and CI share the state safely: the lock in S3 stops two applies running at once.

The outputs are not stored anywhere else, not in `.env` nor in GitHub. They are in the state, and you read them when needed: `terraform output -raw address` (for DNS and `setup.sh`) and `terraform output -raw ssh_user`. The load-test workflow reads them the same way after its apply. The IP stays the same across reinstalls.

**5. DNS.** `A` records for `loadtest.example.com` and `www.loadtest.example.com` pointing at the `address` output. The IP stays the same across reinstalls.

**6. The `.env` for this VPS.** The same keys as prod's (step 4), with the load-test values. Keep it as the GitHub secret `LOADTEST_ENV` (the whole file), and as a local file for running the setup by hand.

- `DOMAIN=loadtest.example.com`, and the same domain in `APP_URL`, `CORS_ALLOWED_ORIGINS` and `MAGIC_LINK_VERIFY_URL`.
- Its own S3 bucket and IAM keys, set up like prod's but never prod's. `BACKUP_AWS_*` can be any placeholder: no backups run here.
- No Sentry DSNs, so load-test errors don't land in prod's projects.
- `OPENAI_API_KEY` and `VOYAGE_API_KEY` empty for now: the load-test keys come in step 2 of the list above. Until then `worker-ingest` restarts in a loop; `/health` still answers.

**7. Bring Kith up.** From the repo root, with your own key in your agent and the host key trusted:

```sh
echo "<address> $(cut -d' ' -f1,2 ~/.ssh/kith-loadtest-host.pub)" >> ~/.ssh/known_hosts
GHCR_USER=<github user> GHCR_TOKEN=<read:packages token> \
  sh infra/loadtest/setup.sh root@<address> <image tag> loadtest.env
```

`<image tag>` is the full SHA of a `master` commit, whose images are in GHCR.

It waits for SSH, installs Docker and the firewall as in step 3, creates `deploy`, copies the infra files and `.env`, runs `deploy.sh`, and ends by fetching `https://loadtest.example.com/health`. It can be run again on the same VPS. A reinstall wipes Caddy's certificates, so each setup asks for new ones: Let's Encrypt gives the same name at most 5 a week, and Caddy then gets them from ZeroSSL instead. Unlike prod, root SSH stays on (keys only), so the script can always get back in. CI logs in to GHCR with its own job token.

**Reinstall** (every file on the VPS is lost):

```sh
cd infra/loadtest/hostinger && sh recreate.sh
```

It calls Hostinger's `recreate` and waits until the VPS runs again. Then run `setup.sh` as above to bring Kith back.

**GitHub secrets and variables from the terminal.** The steps above name them; the web page is repo settings → Secrets and variables → Actions. `gh` reads a file as it is, so multi-line values (keys, the `.env`) can't pick up Windows line endings from the clipboard. Run these before deleting the local files:

```sh
gh secret set HOSTINGER_API_TOKEN               # prompts for the value
gh secret set TERRAFORM_AWS_ACCESS_KEY_ID
gh secret set TERRAFORM_AWS_SECRET_ACCESS_KEY
gh variable set TERRAFORM_AWS_REGION --body <bucket region>
gh secret set LOADTEST_SSH_KEY < ~/.ssh/kith-loadtest
gh secret set LOADTEST_SSH_HOST_KEY < ~/.ssh/kith-loadtest-host
gh secret set LOADTEST_ENV < loadtest.env
# the terraform.tfvars values, for the load-test workflow's apply
gh variable set TF_VAR_data_center_id --body <id>
gh variable set TF_VAR_template_id --body <id>
gh variable set TF_VAR_authorized_keys --body '["ssh-ed25519 AAAA... your-laptop", "ssh-ed25519 AAAA... kith-loadtest"]'
rm ~/.ssh/kith-loadtest   # CI's private key now lives only in GitHub
```

## Day-to-day

Looking after the running server (checking the database, ...) is in `vps-operations.md`.

| Task                        | Command (on the VPS, in `/opt/kith`)                                                              |
| --------------------------- | ------------------------------------------------------------------------------------------------- |
| Follow logs                 | `dc logs -f app` (or `worker-ingest`, `frontend`, `caddy`)                                        |
| Search JSON logs            | `dc logs app --no-log-prefix \| jq 'select(.level=="ERROR")'`                                     |
| Run a script                | `dc exec app python -m scripts.<name> ...`                                                        |
| DB from your laptop         | `ssh -L 5432:localhost:5432 deploy@<vps>`, then connect to `localhost:5432`                       |
| OpenSearch from your laptop | `ssh -L 9200:localhost:9200 deploy@<vps>`, then `curl localhost:9200/_cat/indices`                |
| Roll back                   | Actions → Deploy → Run workflow with an older full commit SHA (step 8)                            |
| Deploy by hand              | `sh deploy.sh <full commit sha>` (what the workflow runs)                                         |
| Apply a `.env` change       | `dc up -d --no-deps app worker-ingest frontend caddy` (step 4); `dc restart` keeps the old values |
| Memory use                  | `docker stats --no-stream`                                                                        |
