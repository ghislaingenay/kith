# Search quickstart

How to run OpenSearch locally, create the index, and look at Chunks. Index shape and the reasons for it are in ADR-0012.

## WSL2: raise the memory-map limit first

OpenSearch will not start if the host allows too few memory maps. On WSL2, set it from a WSL shell:

```sh
sudo sysctl -w vm.max_map_count=262144
```

This resets when WSL restarts. To keep it, add `vm.max_map_count=262144` to `/etc/sysctl.conf` inside the distro (and run `sudo sysctl -p`), or add `kernelCommandLine = sysctl.vm.max_map_count=262144` under `[wsl2]` in `%UserProfile%\.wslconfig` and run `wsl --shutdown`.

If the `opensearch` container exits right after starting, this setting is the usual cause: check `docker compose -f infra/docker-compose.yml logs opensearch` for `max virtual memory areas vm.max_map_count [65530] is too low`.

## Start the services

```sh
make up
```

This starts OpenSearch (http://localhost:9200, version 2.19.1, single node, security off: development only) and Dashboards (http://localhost:5601). The API and the ingest worker wait for OpenSearch to be healthy before they start.

## Create the index

The index and its alias (`kith-chunks`) are created by a script, not by the API:

```sh
make search-index-create
```

Running it again changes nothing. The API checks at startup that the alias exists and refuses to start if it does not, so on a fresh setup the first `make up` leaves the API stopped until the script has run. Start it again afterwards:

```sh
make service-refresh service=app
```

The same applies to the ingest worker (`make service-refresh service=worker-ingest`) if it needed the index.

## Look at Chunks in Dashboards

1. Open http://localhost:5601 and choose **Dev Tools** from the menu.
2. List the indices: `GET _cat/indices/kith-chunks-*?v`
3. See the mapping: `GET kith-chunks/_mapping`
4. Look at some Chunks: `GET kith-chunks/_search` (the vector field is empty until the embedding phase).
5. To browse them as a table, create an index pattern named `kith-chunks*` under **Stack Management** and open **Discover**.

To check the keyword analysis, ask OpenSearch how it reads a text:

```
POST kith-chunks/_analyze
{ "field": "text", "text": "Résumé of the client’s contract" }
```

You should see `resume` and `résumé` both, and `client's` with a straight apostrophe.
