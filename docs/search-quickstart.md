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

### After the mapping changes

While the project is in development, a field added to the mapping (the `deleted` flag on Chunks was the last) does not bump the mapping version, and `make search-index-create` does nothing when the alias already exists. An index built before the change keeps the old mapping and rejects the new field. Add the field to it, keeping its Chunks:

```sh
make refresh-index
```

Running it again changes nothing. Chunks indexed before the field existed simply do not have it; for `deleted` that reads as not deleted. Check the result with `GET kith-chunks/_mapping`: it should list `deleted` as `boolean`.

To start again from nothing, see the next section.

## Start again with no Documents

For development only, and it cannot be undone:

```sh
make clean-documents
```

It asks you to type `yes` first (`make clean-documents yes=1` skips that). It then deletes every Document, Chunk and Upload in every Tenant, including their pages and dead letters, deletes their files from storage, deletes the search index with all its versions and creates it again empty. It deletes only the files the Documents and Uploads point to, never the bucket or anything else in it. If it stops part-way, run it again.

## Look at Chunks in Dashboards

1. Open http://localhost:5601 and choose **Dev Tools** from the menu.
2. List the indices: `GET _cat/indices/kith-chunks-*?v`
3. See the mapping: `GET kith-chunks/_mapping`
4. Look at some Chunks: `GET kith-chunks/_search` (the vector field is empty until the embedding phase; `deleted` is `true` once the Chunk's Document is deleted, and missing before).
5. To browse them as a table, create an index pattern named `kith-chunks*` under **Stack Management** and open **Discover**.

To check the keyword analysis, ask OpenSearch how it reads a text:

```
POST kith-chunks/_analyze
{ "field": "text", "text": "Résumé of the client’s contract" }
```

You should see `resume` and `résumé` both, and `client's` with a straight apostrophe.

## Replay failed indexing and embedding batches

When the search store is down or refuses a batch, ingestion does not retry forever: it marks those Chunks `failed`, records an `open` Chunk Dead Letter row, and leaves the Document `partial` (or `failed` if nothing was indexed). Embedding does the same when Voyage is down or rejects a batch, with a row for stage `embedding`. Once OpenSearch and Voyage are healthy again, replay the open rows:

```sh
make search-replay
```

Replay re-indexes only the failed Chunks, from the text kept in Postgres. It does not read the PDF or storage and does not re-chunk. For each row that works it marks the Chunks indexed, resolves the row, and recomputes the Document, which goes back to `processing` at the `embedding` stage once all its Chunks are indexed. A batch that fails again stays `open` and its attempt count goes up, so you can run replay again later. For each Document with a row that works, it also queues an `embed_document` job (`embed:{document_id}`), so the re-indexed Chunks get vectors; a row that fails again or whose Document was deleted queues nothing, and if that embedding then fails it becomes its own `embedding` row while the `indexing` one stays resolved (ADR-0014). With no open rows it does nothing and succeeds.

Open `indexing` rows are replayed first, then open `embedding` ones. An embedding replay re-embeds exactly the row's Chunks from the text kept in Postgres, through the same provider and circuit breaker, and writes the vectors onto the existing index documents. For each row that works it marks the Chunks embedded and resolves the row, and the Document is worked out again: `ready` once every Chunk is indexed and embedded, `partial` while some are still failed. A row whose Document was deleted, or whose Chunks no longer exist, is resolved without calling Voyage. As with indexing, there is no cap on attempts (ADR-0014).

To limit a run to one stage, one Document or to the oldest few rows:

```sh
make search-replay stage=indexing
make search-replay stage=embedding
make search-replay document=<document-uuid>
make search-replay limit=10
```

To see what is waiting: `SELECT document_id, attempts, error FROM chunk_dead_letters WHERE status = 'open';`

## Embed Documents waiting for vectors

A Document that finished indexing before the embedding phase existed, or whose `embed_document` job was lost, waits at the `embedding` stage (or is `partial`) with no job in the queue. To queue one for each:

```sh
make embed-documents
make embed-documents document=<document-uuid>
```

The command only adds `embed_document` jobs (`embed:{document_id}`) for Documents that are `processing` at `embedding` or `partial`, in every Tenant (a `failed`, `ready` or deleted Document is not queued; a `partial` Document whose indexed Chunks all have vectors already is queued and the job embeds nothing); with `document=` it adds the job for that Document only, if it is waiting. It never calls the embedding provider: the ingest worker does the embedding, under its retries and circuit breaker (ADR-0014). Running it again is safe: a Document whose job is already queued or running is not queued again, and a job only embeds Chunks that still wait for a vector. The worker (`worker-ingest`) must be running for the jobs to be picked up.
