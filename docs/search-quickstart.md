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

## Replay failed indexing batches

When the search store is down or refuses a batch, ingestion does not retry forever: it marks those Chunks `failed`, records an `open` Chunk Dead Letter row, and leaves the Document `partial` (or `failed` if nothing was indexed). Once OpenSearch is healthy again, replay the open rows:

```sh
make search-replay
```

Replay re-indexes only the failed Chunks, from the text kept in Postgres. It does not read the PDF or storage and does not re-chunk. For each row that works it marks the Chunks indexed, resolves the row, and recomputes the Document, which goes back to `processing` at the `embedding` stage once all its Chunks are indexed. A batch that fails again stays `open` and its attempt count goes up, so you can run replay again later. With no open rows it does nothing and succeeds.

To limit a run to one Document or to the oldest few rows:

```sh
make search-replay document=<document-uuid>
make search-replay limit=10
```

To see what is waiting: `SELECT document_id, attempts, error FROM chunk_dead_letters WHERE status = 'open';`
