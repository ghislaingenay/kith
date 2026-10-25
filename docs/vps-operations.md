# VPS operations

How to look after Kith once it runs on the VPS. Setting the server up the first time is in `deploy-quickstart.md`.

Run the commands as `deploy` on the VPS (`ssh deploy@<vps>`). They use full paths, so they work from any folder.

## Check the Postgres database

Open a database shell inside the Postgres container:

```sh
docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env exec postgres psql -U kith -d kith
```

`kith` is the `POSTGRES_USER` and `POSTGRES_DB` from `/opt/kith/.env`; use your values if you set others. No password is asked: the connection comes from inside the container.

The prompt starts with the database's name, e.g. `kith=#`. Then:

| Type | Shows |
|---|---|
| `\dt` | all tables |
| `\d <table>` | a table's columns |
| `SELECT count(*) FROM <table>;` | how many rows a table has (SQL ends with `;`) |
| `\q` | quit |

A prompt ending in `-#` (e.g. `kith-#`) means a line without `;` is still waiting, and psql joins it to whatever you type next, usually into a syntax error. `\r` or Ctrl+C clears it.

### One query, without the psql prompt

`-c` runs one command and returns to the VPS shell. Nothing can be left waiting from an earlier line, so it is the simplest way to look something up. Put the query in double quotes:

```sh
docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env exec postgres psql -U kith -d kith -c "SELECT * FROM tenants;"
```

Change only the text inside the quotes for another query, e.g. `-c "\dt"` to list the tables.

From a graphical tool on your laptop instead: open a tunnel with `ssh -L 5432:localhost:5432 deploy@<vps>`, then connect the tool to `localhost:5432` with the user and password from `/opt/kith/.env`. Postgres listens on the VPS's `127.0.0.1` only, so the tunnel is the only way in from outside.

## Check the logs

The API (`app`) and the worker (`worker-ingest`) write one JSON object per line, with a `level` of `DEBUG`, `INFO`, `WARNING` or `ERROR`. Sentry only receives crashes and a few chosen problems; everything else is only here.

Warnings and errors from the API in the last 24 hours:

```sh
docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env logs --no-log-prefix --since 24h app | grep -E '"level": "(WARNING|ERROR)"'
```

The same for the worker, which processes uploaded Documents:

```sh
docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env logs --no-log-prefix --since 24h worker-ingest | grep -E '"level": "(WARNING|ERROR)"'
```

Change `24h` for another window, e.g. `30m` or `7d`. `--no-log-prefix` drops the `app-1  | ` Docker puts in front of each line, so every line is plain JSON.

Everything one request logged, by its request ID (the `X-Request-ID` response header, or the `request_id` on a Sentry event):

```sh
docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env logs --no-log-prefix app | grep '<request-id>'
```

### Logs from before the last deploy

`docker compose logs` only reads the containers running now, and every deploy replaces the `app` and `frontend` containers (`docker rollout`). Docker writes all container logs to the system journal (the `journald` setup in `deploy-quickstart.md`), so the older ones are still there; `journalctl` reads them by service name, across every container that service has had:

```sh
journalctl COM_DOCKER_COMPOSE_SERVICE=app --since "24 hours ago" -o cat | grep -E '"level": "(WARNING|ERROR)"'
```

Swap `app` for `worker-ingest`, `frontend` or `caddy`, and the grep for `grep '<request-id>'` to follow one request. `--since` also takes a date, e.g. `--since "2026-10-25 14:00"`. `-o cat` prints only the log line, the same JSON as `docker compose logs`.

The journal is capped at 1 GB (`SystemMaxUse` in `/etc/systemd/journald.conf`) and drops the oldest entries first; `journalctl --disk-usage` shows how much it holds.

If the `journalctl` command prints nothing, check the setup: `docker info --format '{{.LoggingDriver}}'` must print `journald`. If it does, look at the fields one log entry really carries, and use the service field it shows in place of `COM_DOCKER_COMPOSE_SERVICE`:

```sh
journalctl -o verbose -n 1 CONTAINER_NAME="$(docker ps --format '{{.Names}}' | grep -m1 app)"
```
