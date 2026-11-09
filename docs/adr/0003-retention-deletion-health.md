# 0003 — Retention, deletion, health, and dead letters

Status: accepted. Built.

## Context

The agent database was unbounded. Messages, model calls, effects, outbox rows,
approvals, reviews, tasks, and notifications grow forever. There was no way to
delete a conversation or an org. There was no liveness or readiness endpoint, and
a poison command stalled the consumer by stopping it on every retry.

## Decision

### Retention

A purge in the consumer deletes rows older than their window.

| Table | Cutoff |
|---|---|
| messages | 60 days |
| model_calls | 60 days |
| effects | 180 days |
| inbox | 180 days |
| outbox | 180 days |
| tasks | 180 days |
| notifications | 180 days |
| approvals | 730 days |
| reviews | 730 days |
| deletions | 730 days |
| profile, tool facts, summary | kept until deleted |
| plan, working summary | cleared when the next turn starts |
| scratch | 1 hour |

The purge runs hourly on the consumer maintenance loop.

### Deletion

An operator tool hard-deletes one conversation or one org, writes a row to
`deletions`, and refuses to run without `--confirm`. A live conversation lock
blocks the delete, because a running turn could write again.

Deletion is not a bus command. It stays an operator tool until commands are
authenticated (item 12).

### Health

A standard-library HTTP server exposes `/healthz` (alive) and `/readyz` (Postgres
answers). A dependency failure returns 503, not a crashloop. Worker on `8080`,
consumer on `8081`, overridable with `HEALTH_PORT`.

### Dead letters

A poison command (bad JSON, unknown type) is wrapped and written to
`agent.commands.dlq`, then the offset commits. A transient error still stops the
consumer, so the bus redelivers. A replay tool publishes one saved event back to
`agent.commands`.

## Consequences

- The database is bounded. Storage grows with active data only.
- Cross-scope data (`effects`, `outbox`) now carries `org_id` and
  `conversation_id`, populated from the writing code and backfilled from JSON on
  migration.
- Deletion is destructive and permanent. The audit row is the only record.
- A poison event no longer blocks the consumer queue indefinitely.

## Open

- How the operator tool exposes deletion once identity exists (item 12).
- Whether a tenant-initiated delete should be a command event instead of an
  operator tool.
- Archive before delete: the docs archive to object storage for evals before
  rows are purged. That waits on object storage.