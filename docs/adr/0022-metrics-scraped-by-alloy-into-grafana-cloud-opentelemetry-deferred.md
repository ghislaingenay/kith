---
status: accepted
date: 2026-10-26
---

# Metrics are scraped by Alloy into Grafana Cloud; the app sends none, and OpenTelemetry stays deferred

Host, container, Postgres, Redis and Caddy metrics reach Grafana Cloud Free through Grafana Alloy, which runs as one more container on each VPS and reads them from the outside. Server-side latency and errors per route come from Caddy's built-in metrics, which cover every request and need no app code. k6 sends its results to the same Grafana Cloud stack. This goes against the rule in `docs/research/observability-backend-choice.md` that the app sends all telemetry over OTLP. That rule is deferred on purpose: the deploy plan already chose Sentry for errors and traces, and the metrics a load test and on-call need are all available from outside the app. Add OpenTelemetry when Sentry traces stop being enough, or with the move to AWS.

Alert rules and dashboards are files in the repo (`infra/grafana/`), pushed to Grafana Cloud by a workflow whenever they change. People read them on Grafana's website and change them in the repo. The SLOs live in one file with the load-test traffic mix, so the k6 pass/fail limits and the prod alert thresholds never disagree.

## Consequences

- Grafana Cloud Free allows 10,000 active series. Alloy keeps only an allowlist of metrics (CPU, RAM and disk per host and container, Postgres connections, Redis memory and queue length, Caddy latency and status per route) and drops the rest. A check reports the series count.
- Metrics are kept for 14 days. The long-term record of each load-test run is the summary JSON the workflow writes to S3 under `loadtest/`.
- Alloy runs on both VPSes: the load-test VPS for test runs and prod for on-call. Alerts go by Grafana email.
