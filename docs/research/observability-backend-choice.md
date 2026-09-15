# Observability backend choice (logs + traces + metrics + alerting, near-zero cost)

Context: FastAPI API + Python arq worker + Next.js frontend on one VPS via
docker-compose, 1 to 50 users, target 2 to 4 GB RAM. All sources below are
primary (official pricing pages, official docs, official GitHub READMEs) and
were read on **2026-09-14** unless stated otherwise. Anything marked
*(secondary)* is not from a vendor page.

## Recommendation

**Non-negotiable design rule:** the application (API, worker, frontend
server) only ever talks to an OTLP endpoint configured from environment
variables (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`,
`OTEL_EXPORTER_OTLP_PROTOCOL`). No vendor SDK, no vendor-specific log
shipper in app code. Structured JSON logs go through the OTel logs SDK (or
an OTel Collector `filelog` receiver reading container stdout), traces
through the OTel traces SDK, metrics through the OTel metrics SDK. That makes
every option below a config change, not a code change.

### Local development: `grafana/otel-lgtm` (one container)

- One `docker run -p 3000:3000 -p 4317:4317 -p 4318:4318 grafana/otel-lgtm`
  gives an OTel Collector, Prometheus, Tempo, Loki, Pyroscope and Grafana in
  a single image. Source: https://github.com/grafana/docker-otel-lgtm
- OTLP for all three signals on 4317/4318; Grafana UI with the same
  datasources you would use in Grafana Cloud, so dashboards and alert rules
  port over. Source: https://github.com/grafana/docker-otel-lgtm
- Apache-2.0. Source: https://github.com/grafana/docker-otel-lgtm
- Explicitly "intended for development, demo, and testing environments", so
  it is a dev tool only. Source: https://grafana.com/docs/opentelemetry/docker-lgtm/

Runner-up for dev: OpenObserve single container (below) if you pick
OpenObserve for production and want dev/prod parity.

### Production on a 2 to 4 GB VPS: Grafana Cloud Free tier (hosted)

Reasoning against the stated criteria:

| Criterion | Grafana Cloud Free |
|---|---|
| OTLP for logs, traces, metrics | Yes, one endpoint `https://otlp-gateway-<REGION>.grafana.net/otlp` for all three. https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/ |
| Alerting included | Yes; the Free plan is "the same managed observability stack (metrics, logs, traces, profiles, dashboards, alerting) that paid plans use". https://grafana.com/docs/grafana-cloud/introduction/ |
| RAM on the VPS | 0 MB (optionally a ~100 MB OTel Collector sidecar for batching/retry). |
| Free ceiling vs ~1 GB logs/month | 50 GB logs + 50 GB traces per month, 10k active metric series, 14-day retention: ~50x headroom. https://grafana.com/pricing/ |
| Operational simplicity | Zero containers to run or back up. |
| Cost | $0, no credit card required for Free. https://grafana.com/pricing/ |

The trade-offs: 14-day retention, 3 active Grafana users, telemetry leaves
the VPS. If any of those is unacceptable (data-residency, >3 people needing
dashboards), use the self-hosted fallback below.

### Self-hosted fallback for production: OpenObserve (one container)

- Single binary / single container, AGPL-3.0, OTLP for logs, metrics and
  traces, built-in scheduled and real-time alerts across logs, metrics and
  traces with email and webhook destinations. Sources:
  https://github.com/openobserve/openobserve ,
  https://openobserve.ai/docs/ingestion/logs/otlp/ ,
  https://openobserve.ai/docs/user-guide/alerts/alerts/
- No documented minimum RAM (see open questions), but it is the only
  self-hosted option here that is one process; SigNoz and HyperDX both
  document a 4 GB minimum, which is the entire VPS.

Why not the others for production on 2 to 4 GB: SigNoz needs "At least 4GB
of memory allocated to Docker" and 5 containers
(https://signoz.io/docs/install/docker/); HyperDX needs "at least 4GB of RAM
and 2 cores" (https://github.com/hyperdxio/hyperdx); Grafana + Loki + Tempo +
Prometheus is 4 containers with 4 config files and no documented minimum,
fine but the most operational surface for the least gain over OpenObserve.

## A. Hosted options with a free tier (read 2026-09-14)

| Vendor | Free logs | Free traces | Free metrics | Retention | Users | Alerting on free | OTLP logs / traces / metrics | Pricing URL |
|---|---|---|---|---|---|---|---|---|
| Grafana Cloud Free | 50 GB/mo | 50 GB/mo | 10k active series | 14 days | 3 active Grafana users, 3 IRM users | Yes | Yes / Yes / Yes | https://grafana.com/pricing/ |
| Axiom Personal | 500 GB/mo ingest total, 25 GB storage, 10 GB-hours query | (same pool) | (same pool, separate "Metrics" dataset) | 30 days | 1 user, 3 datasets, 3 monitors (see per-option note) | Yes ("Yes" in monitors row) | Yes / Yes / Yes (metrics protobuf only) | https://axiom.co/pricing |
| Honeycomb Free | 20M events/mo (logs and spans share this) | (same pool; each span = 1 event) | 100M metric data points/mo | 60 days events/logs, 13 months metrics | not stated on pricing page | 2 triggers | Yes / Yes / Yes | https://www.honeycomb.io/pricing |
| Better Stack Free | 3 GB, 3 days | 3 GB, 3 days | 30 GB | 3 days (logs/traces) | not stated | Slack and email alerts listed (Uptime); telemetry alerts not gated on the page | Yes / Yes / Yes | https://betterstack.com/pricing |
| New Relic Free | 100 GB/mo ingest total | (same pool) | (same pool) | at least 8 days | 1 full platform user | Yes | Yes / Yes / Yes | https://newrelic.com/pricing |
| Datadog | No free logs | No free APM | Free infra plan: 5 hosts, 1-day metric retention | 1 day | n/a | n/a | OTLP via "OTLP APM Ingest" (paid) | https://www.datadoghq.com/pricing/ |
| SigNoz Cloud | No perpetual free tier; 30-day trial, then $49/mo incl. $49 usage; $0.3/GB logs, $0.3/GB traces, $0.1/M metric samples | | | 15 days logs/traces, 1 month metrics | unlimited | Yes | Yes / Yes / Yes | https://signoz.io/pricing/ |
| OpenObserve Cloud | No perpetual free tier on the pricing page; 14-day trial of Pay-As-You-Go | | | 30 days non-metrics, 15 months metrics | unlimited | Yes | Yes / Yes / Yes | https://openobserve.ai/pricing/ |

### Per-option details (hosted)

**Grafana Cloud Free**
- Metrics "Limited to 10k active series per month", "14 days retention"; Logs "Limited to 50 GB ingested per month", "14 day retention"; Traces "Limited to 50 GB ingested per month", "14 day retention"; Grafana "Limited to 3 active users per month"; IRM "Limited to 3 active IRM users per month"; Community support. https://grafana.com/pricing/
- Free plan includes alerting: "metrics, logs, traces, profiles, dashboards, alerting". https://grafana.com/docs/grafana-cloud/introduction/
- OTLP: "The Grafana Cloud OTLP endpoint is OpenTelemetry Protocol (OTLP) compliant, and the recommended endpoint to send OpenTelemetry metrics, logs, and traces to Grafana Cloud." Base `https://otlp-gateway-<REGION>.grafana.net/otlp`, SDK appends `/v1/{metrics,logs,traces}`. https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/

**Axiom Personal**
- "$0/month, permanent", "500 GB / mo" data loading, "10 GB-hours / mo" query compute, "25 GB" storage, "30 days" retention, no credit card, monitors/alerting "Yes". Next tier "$25/mo platform fee + usage". https://axiom.co/pricing
- Personal plan restrictions of 1 user, 3 datasets, 3 monitors, 30 days were returned from https://axiom.co/docs/reference/field-restrictions ; the pricing page itself did not show user/dataset/monitor rows, so treat the 1 user / 3 datasets / 3 monitors figures as needing re-verification (open question).
- OTLP: separate `/v1/traces`, `/v1/logs`, `/v1/metrics` endpoints; "The /v1/metrics endpoint only supports the application/x-protobuf content type"; logs/traces go to an "Events" dataset, metrics need a "Metrics" dataset. With 3 datasets on Personal that is exactly logs+traces (1 or 2) and metrics (1). https://axiom.co/docs/send-data/opentelemetry

**Honeycomb Free**
- "Event Volume: Up to 20M per month", "Metrics Data Points: Up to 100M per month", "2 Triggers", SLOs not included, "OpenTelemetry Support" included. https://www.honeycomb.io/pricing
- Retention: "Events and logs: 60-day fixed retention", "Time-series metrics datasets: 13-month fixed retention by default"; "Honeycomb counts each span in a trace as an event". https://docs.honeycomb.io/get-started/manage-costs/how-honeycomb-calculates-usage
- OTLP: "Honeycomb supports receiving telemetry data via OpenTelemetry's native protocol, OTLP, over gRPC, HTTP/protobuf, and HTTP/JSON"; `https://api.honeycomb.io/v1/{traces|metrics|logs}` or gRPC `api.honeycomb.io:443`. https://docs.honeycomb.io/send-data/opentelemetry/
- Note: 1 GB/month of ~1 KB JSON log lines is about 1M events; spans add to the same 20M pool. Only 2 triggers is the tightest alerting ceiling of the group.

**Better Stack Free**
- "3 GB logs retained for 3 days", "3 GB traces retained for 3 days", "30 GB metrics"; Uptime: "10 monitors & heartbeats, 1 status page", "Slack & e-mail alerts". https://betterstack.com/pricing
- OTLP: `https://$INGESTING_HOST/v1/traces`, `/v1/metrics`, `/v1/logs`, `Authorization: Bearer $SOURCE_TOKEN`. https://betterstack.com/docs/logs/open-telemetry/
- Telemetry alerts are created from dashboard charts (threshold, percentage change, anomaly) with email default plus call/SMS/push; no free-plan restriction stated on that page. https://betterstack.com/docs/logs/dashboards/alerts/
- 3-day retention is the shortest of the group; 3 GB/month is only ~3x the 1 GB target.

**New Relic Free**
- "100 GB of free data ingest per month", "Default data retention of at least 8 days", "One free full platform user", alerts included. https://newrelic.com/pricing
- "You have access to 100 GB Ingested per month for free." https://docs.newrelic.com/docs/accounts/accounts-billing/new-relic-one-pricing-billing/new-relic-one-pricing-billing/
- OTLP: "New Relic supports native OTLP ingest and recommends it as the preferred method"; `https://otlp.nr-data.net` (ports 443, 4317, 4318), EU `https://otlp.eu01.nr-data.net`, `api-key` header; logs, traces, metrics all accepted (metrics should use delta temporality). https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-otlp/
- Caveat: only 1 full-platform user; 8-day retention.

**Datadog**
- Free plan is infrastructure only: "Up to 5 hosts", "1 day" metric retention, "Core collection and visualization features". No free logs or APM. Paid: Infrastructure Pro "$15 per host, per month", Logs "$0.10 per ingested or scanned GB", APM "$31 per host, per month". OTLP appears as a paid "OTLP APM Ingest" tier. https://www.datadoghq.com/pricing/
- Not a candidate at zero cost.

**SigNoz Cloud**
- "Starts at $49/month, including $49 of usage"; Logs "$0.3/GB ingested", Traces "$0.3/GB ingested", Metrics "$0.1/mn samples"; "15 days retention" logs/traces, "1 month retention" metrics; "unlimited teammates"; alerting included; OTLP native. https://signoz.io/pricing/
- "30-day trial" with "no credit card required". https://signoz.io/teams/
- Not zero cost after the trial.

**OpenObserve Cloud**
- "14-day free trial on the Pay As You Go plan - no credit card required"; retention "15 months" metrics, "30-Days" non-metrics; unlimited users; no limits on "dashboards, alerts, or data sources". No perpetual free tier is listed on the page as read. https://openobserve.ai/pricing/
- Not zero cost after the trial (as of this reading).

## B. Self-hosted in docker-compose

| Stack | Containers | Documented min RAM | OTLP logs / traces / metrics | Alerting built in | License | Quickstart |
|---|---|---|---|---|---|---|
| Grafana + Loki + Tempo + Prometheus | 4 (Alertmanager not needed: Grafana has a built-in one; +1 optional OTel Collector) | none documented | Loki: yes (`/otlp`); Tempo: yes (4317/4318); Prometheus: yes (`/api/v1/otlp/v1/metrics` with `--web.enable-otlp-receiver`) | Yes, Grafana Alerting with built-in Alertmanager | Grafana AGPL-3.0, Loki AGPL-3.0, Tempo AGPL-3.0, Prometheus Apache-2.0 *(licenses from repo LICENSE files; not re-fetched this session, see open questions)* | Dev all-in-one: https://github.com/grafana/docker-otel-lgtm ; Tempo compose example: https://grafana.com/docs/tempo/latest/getting-started/docker-example/ |
| SigNoz self-hosted | 5 (ClickHouse, ClickHouse Keeper, PostgreSQL, SigNoz OTel Collector, SigNoz backend) + optional MCP server | "At least 4GB of memory allocated to Docker" | Yes / Yes / Yes (4317, 4318) | Yes (metric, log, trace, anomaly, exception alerts; Slack, PagerDuty, Opsgenie, MS Teams, email, webhooks) | MIT (Expat) except `ee/` and `cmd/enterprise/` (proprietary); Foundry installer AGPL-3.0 | https://signoz.io/docs/install/docker/ |
| OpenObserve self-hosted | 1 (single binary) | none documented | Yes / Yes / Yes (HTTP `/api/<org>/v1/{logs,metrics,traces}`, gRPC :5081) | Yes (scheduled, real-time, composite; email, webhook, actions) | AGPL-3.0 | https://openobserve.ai/docs/quickstart/ |
| HyperDX | 4 in compose (app, otel-collector, ch-server, db=MongoDB); or 1 all-in-one image (demo/testing only) | "at least 4GB of RAM and 2 cores for testing" | Yes / Yes / Yes (4317, 4318) | Yes | MIT | https://github.com/hyperdxio/hyperdx ; all-in-one: https://clickhouse.com/docs/use-cases/observability/clickstack/deployment/all-in-one |

### Per-option details (self-hosted)

**Grafana + Loki + Tempo + Prometheus**
- Loki: "Loki natively supports ingesting OpenTelemetry logs over HTTP", endpoint `http://<loki-addr>/otlp`; structured metadata enabled by default in Loki 3.0+. https://grafana.com/docs/loki/latest/send-data/otel/
- Prometheus: OTLP received at `/api/v1/otlp/v1/metrics`, enable with `--web.enable-otlp-receiver`; "disabled by default" because Prometheus has no auth. https://prometheus.io/docs/guides/opentelemetry/
- Tempo: the official compose example exposes `4317-4318` on the tempo service. https://grafana.com/docs/tempo/latest/getting-started/docker-example/
- Grafana: "Grafana includes a built-in Alertmanager that extends the Prometheus Alertmanager", external Alertmanager optional. https://grafana.com/docs/grafana/latest/alerting/set-up/configure-alertmanager/
- The single-image `grafana/otel-lgtm` is "intended for development, demo, and testing environments". https://grafana.com/docs/opentelemetry/docker-lgtm/
- Minimum RAM: not documented by Grafana for a small single-node compose. *(secondary, from experience: each of Loki/Tempo/Prometheus/Grafana idles at roughly 100 to 300 MB, so ~1 GB total is a reasonable planning number; unverified.)*

**SigNoz self-hosted**
- Install: `curl -fsSL https://signoz.io/foundry.sh | bash`, then `foundryctl cast -f casting.yaml`; services: ClickHouse Server, PostgreSQL, ClickHouse Keeper, SigNoz OTel Collector, SigNoz backend (+ optional MCP server); "At least 4GB of memory allocated to Docker"; ports 8080 UI, 4317/4318 OTLP. Bundled docker-compose files are "deprecated as of v0.130.0" but Foundry generates and runs docker compose underneath. https://signoz.io/docs/install/docker/
- The `deploy/` directory README confirms: "The install.sh script and the docker-compose manifests have been deprecated. SigNoz now installs and runs through Foundry." https://github.com/SigNoz/signoz/blob/main/deploy/README.md
- License: MIT Expat, with `ee/` and `cmd/enterprise/` under `ee/LICENSE`. https://github.com/SigNoz/signoz/blob/main/LICENSE
- Foundry itself is AGPL-3.0. https://github.com/SigNoz/foundry
- Alerts: metrics, logs, traces, anomaly, exceptions; channels Slack, PagerDuty, Opsgenie, MS Teams, email, webhooks. https://signoz.io/docs/alerts/

**OpenObserve self-hosted**
- Single binary: `ZO_ROOT_USER_EMAIL=... ZO_ROOT_USER_PASSWORD=... ./openobserve`; Docker: `docker run -v $PWD/data:/data -e ZO_DATA_DIR=/data -p 5080:5080 ... o2cr.ai/openobserve/openobserve-enterprise:latest` (note the quickstart points at the *enterprise* image; see open questions for the OSS image). No RAM minimum stated. https://openobserve.ai/docs/quickstart/
- "AGPL-3.0", "Single binary deployment", "OpenTelemetry native". https://github.com/openobserve/openobserve
- OTLP HTTP `https://<host>/api/<org>/v1/logs` and gRPC `<host>:5081`; the docs state OTLP is supported "for three signal types: logs, metrics, and traces". https://openobserve.ai/docs/ingestion/logs/otlp/ ; traces `https://<host>/api/<org>/v1/traces`. https://openobserve.ai/docs/ingestion/traces/opentelemetry/ ; metrics via "OTLP / OTEL collector". https://openobserve.ai/docs/ingestion/metrics/
- Alerts: scheduled, real-time, composite (anomaly detection is enterprise); apply to logs, metrics, traces; destinations email, webhook (Slack, Teams, Jira), actions. https://openobserve.ai/docs/user-guide/alerts/alerts/
- Memory behaviour: `ZO_MEM_TABLE_MAX_SIZE` default is "50 percent of total memory"; `ZO_MAX_FILE_SIZE_IN_MEMORY` default 256 MB, so cap memory with a compose `mem_limit` and tune these. https://openobserve.ai/docs/environment-variables/

**HyperDX**
- MIT; `docker run -p 8080:8080 -p 4317:4317 -p 4318:4318 docker.hyperdx.io/hyperdx/hyperdx-all-in-one`; "at least 4GB of RAM and 2 cores for testing"; OTLP for logs, traces, metrics; alerts "in just a few clicks"; all-in-one contains HyperDX UI, OTel Collector, ClickHouse, MongoDB. https://github.com/hyperdxio/hyperdx
- Compose services: `db` (MongoDB), `otel-collector`, `app`, `ch-server`. https://github.com/hyperdxio/hyperdx/blob/main/docker-compose.yml
- All-in-one image (`clickhouse/clickstack-all-in-one`) is for "Demos" and "Local testing"; "Non-persistent storage" unless volumes are mounted, "Lack of component isolation". https://clickhouse.com/docs/use-cases/observability/clickstack/deployment/all-in-one

## Open questions

1. Axiom Personal plan user/dataset/monitor caps (1 / 3 / 3) came back from a docs page whose URL is about field restrictions; confirm on https://axiom.co/pricing plan-comparison rows before relying on Axiom. If the 3-dataset cap holds, it is exactly enough for logs, traces, metrics with nothing spare.
2. OpenObserve publishes no minimum RAM for a single node; the capacity-planning page defers to a spreadsheet (https://openobserve.ai/docs/enterprise-setup/capacity-planning/). Measure idle and 1 GB/month RSS on the VPS before committing; set `mem_limit` and `ZO_MEM_TABLE_MAX_SIZE`.
3. OpenObserve's quickstart docker command uses the `openobserve-enterprise` image. Confirm the OSS (AGPL) image name/tag from the GitHub README before deploying, so the licence you rely on matches the binary you run.
4. Honeycomb's pricing page does not state a Free-plan user limit; check before choosing it for a multi-person team.
5. Grafana/Loki/Tempo licences (AGPL-3.0) were not re-fetched this session; confirm from each repo's LICENSE file if AGPL matters for your distribution model (it does not for running a hosted service internally).
6. Grafana Cloud Free's 10k active series ceiling: a FastAPI + arq + Next.js app with default OTel HTTP metrics and histogram buckets can approach this if route cardinality is high; set the OTel metric views to bound label cardinality.
7. Whether to run a local OTel Collector on the VPS in front of the OTLP env-var endpoint (adds ~100 MB, gives batching, retry, tail sampling, and stdout-JSON log tailing without an in-process logs exporter). Recommended but not yet decided.
