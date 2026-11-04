# 0004 — Metrics, traceparent, and quotas

Status: accepted. Metrics and traceparent built; quotas are a partial guard.

## Context

The service had no visibility outside its Postgres tables and no limit on how
much one org could drive the worker. EDA §9 asks for four numbers (run success
rate, p99 turn latency, cache hit ratio, consumer lag) and §6 asks for priority
and fairness.

There is no OpenTelemetry collector in this environment. Shipping an exporter
with nothing to export to would be dead code.

## Decision

### Metrics

Compute the four numbers from Postgres and serve them as Prometheus text on the
health server (`GET /metrics`). The same queries feed a real exporter when one
is added.

- Success rate: distinct runs with a `started` minus a `failed` event, 7 days.
- p99 latency: paired `started`/`completed` run events joined on `run_id`, 7 days.
- Cache hit ratio: `cache_hit / (cache_hit + cache_miss)` over recent model calls.
- Consumer lag: age of the newest run event. **Approximation**; exact lag needs a
  Kafka admin client.

### traceparent

Propagate the envelope's `traceparent` into the run request and onto the three
`agent.run.*` events. No exporter runs; the id is carried so a trace can be
reassembled later. This is the EDA §9 "propagate traceparent" contract, without
a dead backend.

### Quotas and priority

`MAX_ACTIVE_RUNS` per org: interactive 2, routine 1, backfill 1. Measured from
live `conversation_locks` rows.

- **Interactive is never dropped.** A busy interactive turn outranks background work.
- **routine/backfill over the cap are skipped.** The offset still commits, so the
  command is not retried. This is a guard, not a queue.

## Consequences

- The four numbers are visible over HTTP with `curl :8081/metrics`.
- Trace ids follow a turn end to end on the run events.
- One org cannot flood the worker with interactive turns.
- A skipped routine message is dropped, not queued. That is the limit of the
  guard; a queue or preemption would keep it.

## Deferred

- Real OTel export and distributed spans across channel/bus/sandbox.
- Preemption (yield a running routine on an interactive message) — changes the
  workflow signal surface.
- Batching several quick messages into one turn — needs a drain window.
- Per-org concurrency quotas on the Temporal task queue.
- Exact consumer lag via a Kafka admin client.