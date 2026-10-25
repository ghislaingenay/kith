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

One query without opening the shell:

```sh
docker compose -f /opt/kith/docker-compose.prod.yml --env-file /opt/kith/.env exec postgres psql -U kith -d kith -c '\dt'
```

From a graphical tool on your laptop instead: open a tunnel with `ssh -L 5432:localhost:5432 deploy@<vps>`, then connect the tool to `localhost:5432` with the user and password from `/opt/kith/.env`. Postgres listens on the VPS's `127.0.0.1` only, so the tunnel is the only way in from outside.
