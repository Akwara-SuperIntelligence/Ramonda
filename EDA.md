# EDA: the agent service in an event-driven system

Scope: **one service** — the always-on agent — as a participant in a larger
microservice, event-driven system. Not the organisation ingestion pipeline, not
the graph-vector store, not the channels. The agent's internals are in
[ACHITECTURE.md](ACHITECTURE.md) and
[reference/architecture-map.html](reference/architecture-map.html); the
Rust/Python split is in [LANGUAGE.md](LANGUAGE.md). Vocabulary follows
[GLOSSARY.md](GLOSSARY.md).

The service keeps the shape from the talk: thin client, thick server, one
`send_user` boundary, one durable run per turn, a disposable computer, memory as
files, and an approval gate on irreversible actions. What changes is **who owns
what** and **how the outside world reaches the loop**.

## 0. Decisions at a glance

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Transport between services | Event bus (at-least-once) | Decoupling, backpressure, fan-out |
| 2 | Orchestration inside this service | Temporal, private | Long runs must resume, not replay |
| 3 | External contract | Events out, commands in | No workflow IDs outside the service |
| 4 | Dedupe | Three layers: inbox, workflow ID, effect token | Every hop is at-least-once |
| 5 | Writes + publish | Transactional outbox | No dual-write inconsistency |
| 6 | Waiting on other services | Subscription table + signal | Never poll |
| 7 | Org knowledge | Called via a `retrieve` tool | The graph is owned by ingestion |
| 8 | Ordering | Partition by `org_id` | Per-conversation order is the requirement |

## 1. Where this service ends

| This service owns | This service calls |
|---|---|
| Conversation and message state | Retrieval (org knowledge, graph-vector) |
| Episodic memory: profile, dated logs, scratchpad, skills | Sandbox control plane (Rust, shared) |
| Run orchestration and harness policy | Secret broker / egress proxy |
| Approval policy and pending approvals | LLM gateway (rate limits, cost attribution) |
| Tool surface offered to the model | Channels / delivery (Slack, email, push) |
| Evals over its own traces | Organisation directory, billing, analytics |

Two rules follow, and they are load-bearing:

- **The agent never writes the graph-vector store.** Ingestion owns that write
  path. The agent reads through retrieval and emits observations as events if
  anyone wants them.
- **No other service knows about Temporal.** No workflow IDs in payloads, no
  signalling our runs from outside, no querying our workflows for status. Status
  is a domain event or a read model.

## 2. Two layers, one owner per process

```
 other services ──events──▶ bus ──▶ consumer ──▶ Temporal ──▶ harness worker
        ▲                  │  dedupe, order,    (private)         │
        │                  │  quota, priority                     │
        └── domain events ─┴──────── outbox ◀──────── Postgres ◀──┘

 platform, shared:  sandbox (Rust) · secrets (Rust) · LLM gateway · channels
 external:          retrieval API → graph-vector DB ← ingestion pipeline
```

- The **bus** carries facts between services.
- **Temporal** carries control flow inside this service.
- **One owner per long-running process.** If a process spans services, exactly
  one workflow owns it and calls the other services' idempotent commands. Never
  encode "and then, and then" as a chain of events — that is a saga nobody can
  trace, cancel, or replay.

Backpressure is a feature of this split: when the service is saturated, the bus
buffers and you observe **consumer lag**, not request errors. Alert on lag, not
on 5xx.

## 3. Contracts

### 3.1 Event envelope

Stable, additive-only, versioned per type. Keep it small; put bulk data in object
storage and pass a URI.

```jsonc
{
  "event_id":       "01J...",          // ULID, unique per emission
  "type":           "agent.run.completed",
  "version":        1,                  // per type, additive changes only
  "occurred_at":    "2026-11-02T10:00:00Z",
  "producer":       "agent-service",
  "org_id":         "org_123",          // tenant; also the partition key
  "actor_id":       "user_456",         // who or what caused it
  "subject":        { "conversation_id": "conv_789", "run_id": "run_abc" },
  "correlation_id": "01J...",           // the causal chain
  "causation_id":   "01J...",           // the command/event that caused this
  "priority":       "interactive",      // interactive | routine | backfill
  "traceparent":    "00-...-...-01",
  "payload":        { }
}
```

Rules: `event_id` is never reused; `type` is namespaced `agent.<noun>.<verb>`;
`payload` is schema-validated in CI; consumers ignore unknown fields and tolerate
unknown types.

### 3.2 Events published

| Event | When | Consumed by |
|---|---|---|
| `agent.message.composed` | The agent wants to say something; carries text plus presentation hints | Channels / delivery |
| `agent.run.started` | A run begins | Analytics, UI read models |
| `agent.run.completed` | Final answer or deliberate silence | Evals, analytics |
| `agent.run.failed` | Terminal failure, with reason class | On-call, evals |
| `agent.approval.requested` | A gate needs a human | Approvals UI, notifications |
| `agent.approval.resolved` | Approved or denied | Audit |
| `agent.observation.recorded` | A durable fact worth sharing | Ingestion (optional) |

Do **not** emit an event per tool call or per model call. That is trace data, not
domain data; it belongs in spans. The bus is for facts other services act on.

### 3.3 Commands accepted

| Command | Caller | Effect |
|---|---|---|
| `SendMessage` | Channels | Signal an active run, or start one |
| `CancelRun` | UI, policy | Graceful yield, then cancel |
| `ResolveApproval` | Approvals service | Unblocks a waiting gate |
| `UpdateRoutine` | UI, admin | Create/change/delete a Temporal Schedule |

Commands are idempotent on `(command_id)`, carry a reply event, and are the only
write path from outside. Everything else is read-only.

### 3.4 Tool surface

The model's tools are the narrow waist: `run_shell`, `send_user`, `remember`,
`recall`, `delegate`, `retrieve`, `browser`. `send_user` is the only tool that
crosses the product boundary, which is why channel changes never touch the
harness. `retrieve` is the only door to organisational knowledge.

## 4. Exactly-once is a lie; here are the three dedupe layers

| Layer | Mechanism | Catches |
|---|---|---|
| Inbox | `inbox(event_id)` unique constraint, written in the same transaction as the effect | Redelivery from the bus |
| Workflow | Workflow ID `run:{conversation_id}:{seq}`, `WorkflowIDConflictPolicy=USE_EXISTING` | Concurrent turns, duplicate starts |
| Effect | Effect token `sha256(run_id, step_index, tool_name)` on every side effect | Activity retry |

- **Outbox.** Write product state and the outgoing event in one Postgres
  transaction; a relay (or CDC) publishes. Never publish from the workflow body,
  and never write the DB and publish as two separate steps.
- **Effect tokens** go into sandbox calls, egress writes, payments, and message
  sends. The receiving side dedupes on the token, not on our retries.
- **Approvals are single-use** with an expiry; a replayed approval event must not
  release a second send.

## 5. Ordering, priority, fairness

- **Partition by `org_id`** (coarse) and require order only within a
  conversation. Cross-conversation ordering is explicitly not guaranteed.
- **Priority classes** live in the envelope so the decision is made by the
  sender, not inferred: `interactive` outranks `routine` outranks `backfill`.
- **Preemption:** an interactive message to a busy conversation does not queue
  behind the run. Signal the active run to yield at its next step; if it does not
  yield within a grace window, cancel it and start the interactive run. Bounded
  cancellation, not a hard kill.
- **Fairness:** per-org concurrency quotas on the harness task queue, plus a
  per-org cap on active runs. One tenant's ingestion backfill must never starve
  another tenant's chat. Measure starvation directly (queue wait p99 per class).
- **Batching:** drain the signal queue for a quiet window (2–5 s) before starting
  a turn. Three quick messages become one turn.

## 6. Waiting without polling

Runs wait on other services (document indexed, backfill complete, retrieval
ready). Temporal has no index of "who is waiting for X", so maintain one:

1. The workflow registers a waiter row: `(subject, run_id, workflow_id, deadline)`.
2. The consumer, on the awaited event, looks up waiters by subject and signals
   each workflow.
3. **Race:** the event may arrive before the waiter registers. The consumer
   records the event in a per-subject `pending` table; the workflow, after
   registering, re-checks `pending` inside a `wait_condition`. Register → re-check
   closes the gap.
4. Always set a deadline. A wait without a timeout is an outage waiting to happen;
   on expiry, mark the dependency degraded and let the run finish with a caveat.

## 7. Memory: episodic owned, organisational called

| Layer | Lives in | Owner | Read when |
|---|---|---|---|
| Core facts | Profile file, in every prompt | This service | Every turn |
| Dated logs | Files in the sandbox | This service | Searched on demand |
| Scratchpad | Files, ephemeral | This service | This hour, then discarded |
| Skills | Markdown files | This service | On demand |
| Org knowledge | Graph-vector DB | Ingestion | Via `retrieve`, lazily |

Consequences: no second vector index in this service; retrieval results are
written to a file and the **path** is returned to context, not the document body;
retrieved text is untrusted input and never treated as an instruction.

## 8. Observability

- Propagate `traceparent` from the envelope into Temporal via client interceptors
  and activity headers, so one trace spans channel → bus → workflow → tool →
  sandbox.
- Span attributes: `org_id`, `conversation_id`, `run_id`, `step_index`,
  `tool_name`, `model`, `cache_hit`, `tokens_in/out`.
- Cost attribution happens at the LLM gateway, keyed by `org_id`; do not
  reconstruct billing from logs.
- Log JSON with IDs, not prose. Log prompt **hashes** and object-store refs by
  default; full prompts only behind a flag, with retention limits and no secrets.
- The four numbers that matter: run success rate, p99 turn latency, cache hit
  ratio, consumer lag.

## 9. Versioning and evolution

The talk's "delete the product" applies to the harness, not to the contracts.

- **Event schemas:** version per type, additive-only, registry checked in CI,
  contract tests on both producer and consumer. Removing or retyping a field is a
  new event type.
- **Workflows:** keep them thin and version them. Enable Temporal worker
  versioning (build IDs) where your SDK supports it; otherwise pin workers,
  drain, and deploy. `continue-as-new` before the history limit (~51k events /
  50 MB default) for multi-day runs.
- **Activities:** freely editable; they are not replayed. This is where the
  harness lives, precisely so it can churn monthly.
- **Migrations:** expand/contract for the product database and for event payloads
  alike; both are read by services you do not deploy.

## 10. Failure modes

| Failure | Behaviour | Mitigation |
|---|---|---|
| Consumer crashes mid-effect | Event redelivered | Inbox uniqueness; effect token |
| Workflow waits on approval forever | Run parked | Deadline, then deny and notify |
| Sandbox dies mid-run | Activity fails | Re-provision from snapshot, retry with token |
| LLM gateway 429 / 5xx | Activity retries | Retry policy plus queue-level concurrency cap |
| Retrieval service down | Tool returns degraded | Run proceeds, or waits with deadline |
| Poison event | Retries exhaust | DLQ, alert, run marked failed |
| Workflow fails terminally | No Temporal DLQ | `agent.run.failed` is the DLQ: alert, keep history |
| Consumer lag grows | Turns are late | Lag alert per priority class, scale workers |
| Clock skew on deadlines | Early/late expiry | Server time only, generous jitter |

## 11. Tenancy and Temporal layout

One Temporal cluster, **namespace per bounded context** (or per data-residency
tier where required), task queues per role: `agent-orchestrator`,
`agent-harness`, `agent-helper`. Never a cluster per microservice, never one
namespace shared across teams. Keep retention explicit; archive histories to
object storage for audit because agent runs are evidence.

## 12. Anti-patterns

- Cross-service saga built from events.
- A second orchestrator (bus-driven retries alongside Temporal).
- Workflow IDs, signals, or queries leaking into an external API.
- Other services querying Temporal for status.
- Polling instead of a signal plus a subscription table.
- Eagerly stuffing retrieved org knowledge into the prompt prefix.
- An event per tool call.
- Claiming exactly-once instead of making effects idempotent.
- Unbounded retries with no dead-letter and no owner.

## 13. Build order

0. Temporal dev server, one Python worker, `RunWorkflow`, echo model, CLI client.
   Kill the worker mid-run; watch it resume.
1. Event envelope plus inbox/outbox plus schema tests. No harness yet.
2. Real harness, file memory, container sandbox, approvals via events.
3. Schedules, priority classes, per-org quotas, a stubbed `retrieve`.
4. Rust sandbox platform service behind gRPC; swap the container sandbox.
5. Worker versioning, DLQ and alerting, evals fed from the event log.

## 14. Open questions

- Who owns message rendering and delivery — this service or channels? Decide
  before the first channel integration.
- Per-tenant namespaces versus a shared namespace with quotas: cost against blast
  radius.
- Data residency for org knowledge and for agent memory: same region or not.
- Approval SLA per action class, and what "expired" means for money movement.
- Whether `agent.observation.recorded` should feed ingestion, and under whose
  schema.

## References

- [ACHITECTURE.md](ACHITECTURE.md) — the source talk, sections 01–06.
- [reference/architecture-map.html](reference/architecture-map.html) — the
  one-page map of the product.
- [LANGUAGE.md](LANGUAGE.md) — what is Rust and what is Python, and why.
- [RESOURCES.md](RESOURCES.md) — Temporal durable execution, 12-Factor Agents,
  Firecracker, context engineering.
